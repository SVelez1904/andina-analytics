"""Copia a BigQuery las tablas y vistas que usa el dashboard.

    python -m analitica.subir_bigquery             # sube todo lo de OBJETOS
    python -m analitica.subir_bigquery --dry-run   # solo lee Postgres y muestra conteos
    python -m analitica.subir_bigquery --solo analitica.reportes

Cada schema de Postgres va a un dataset de BigQuery con el mismo nombre (public, analitica),
así el SQL del dashboard puede seguir escribiendo `public.tabla`. Cada tabla se reemplaza entera
(refresco completo). Usa el usuario analitica_app del .env, que NO puede leer datos personales
(dim_hospedes, vw_reservas_analisis, usuarios de Django): eso nunca sale de tu computador.

Requiere GCP_PROJECT en el .env y haber corrido una vez `gcloud auth application-default login`.
"""
import argparse
import datetime as dt
import decimal
import json
import re
import sys
import uuid

import numpy as np
import pandas as pd

from . import db
from .config import BQ_LOCATION, GCP_PROJECT

# Lo que lee el dashboard (app/). Si una página nueva consulta otra tabla o vista, agrégala aquí.
OBJETOS = {
    "public": [
        "vw_fct_noches", "propiedad_fechas", "dim_propiedades",
        "vw_kpis_mercado_mensual", "vw_reviews_actual", "vw_reviews_mensual",
        "vw_controles_calidad", "vw_conversion_fotos", "parametros_conversion", "vw_acciones_impacto",
    ],
    "analitica": [
        "vw_pronostico_actual", "pronostico_noches", "vw_noches_en_riesgo",
        "review_temas", "vw_review_temas_detalle", "vw_pendientes_propiedad", "vw_fortalezas_propiedad",
        "vw_finanzas_reservas", "reportes",
    ],
}


# -- Tipos de Postgres -> tipos que BigQuery acepta ----------------------------------------------

def nombre_bq(nombre):
    """BigQuery solo acepta letras, números y _; no puede empezar con número."""
    limpio = re.sub(r"[^0-9a-zA-Z_]", "_", nombre)
    return f"_{limpio}" if limpio[:1].isdigit() else limpio


def _es_nulo(v):
    return v is None or (isinstance(v, float) and np.isnan(v))


def preparar(df):
    """Convierte las columnas de un DataFrame leído de Postgres a tipos que BigQuery carga bien."""
    df = df.copy()
    df.columns = [nombre_bq(c) for c in df.columns]
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_timedelta64_dtype(s):          # interval -> segundos
            df[col] = s.dt.total_seconds()
            continue
        if s.dtype != object:
            continue
        muestra = s.dropna()
        if muestra.empty:                                  # columna toda vacía: texto
            df[col] = s.astype("string")
            continue
        primero = muestra.iloc[0]
        if isinstance(primero, decimal.Decimal):           # numeric -> FLOAT64
            df[col] = s.map(lambda v: None if _es_nulo(v) or v.is_nan() else float(v)).astype("float64")
        elif isinstance(primero, uuid.UUID):
            df[col] = s.map(lambda v: None if _es_nulo(v) else str(v)).astype("string")
        elif isinstance(primero, list):                    # text[] -> ARRAY<STRING> (vacío en vez de NULL)
            df[col] = s.map(lambda v: [] if _es_nulo(v) else [str(x) for x in v if x is not None])
        elif isinstance(primero, dict):                    # json/jsonb -> texto JSON
            df[col] = s.map(lambda v: None if _es_nulo(v) else json.dumps(v, default=str, ensure_ascii=False))
        elif isinstance(primero, dt.timedelta):
            df[col] = s.map(lambda v: None if _es_nulo(v) else v.total_seconds()).astype("float64")
        elif isinstance(primero, memoryview):
            df[col] = s.map(lambda v: None if _es_nulo(v) else bytes(v))
    df["_cargado_en"] = pd.Timestamp.now(tz="UTC")
    return df


# -- BigQuery -----------------------------------------------------------------------------------

def cliente():
    from google.cloud import bigquery

    if not GCP_PROJECT:
        raise RuntimeError("Falta GCP_PROJECT en el archivo .env (ver .env.example).")
    c = bigquery.Client(project=GCP_PROJECT)
    for schema in OBJETOS:
        ds = bigquery.Dataset(f"{GCP_PROJECT}.{schema}")
        ds.location = BQ_LOCATION
        c.create_dataset(ds, exists_ok=True)
    return c


def subir_df(client, schema, nombre, df):
    from google.cloud import bigquery
    from google.cloud.bigquery.format_options import ParquetOptions

    destino = f"{client.project}.{schema}.{nombre_bq(nombre)}"
    cfg = bigquery.LoadJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
    cfg.parquet_options = ParquetOptions()
    cfg.parquet_options.enable_list_inference = True     # listas -> ARRAY<STRING>, no STRUCT anidado
    client.load_table_from_dataframe(df, destino, job_config=cfg).result()
    return client.get_table(destino).num_rows


def subir(objetos=None, dry_run=False, imprimir=print):
    """objetos: lista de 'schema.tabla' (por defecto, todo OBJETOS). Devuelve la lista de errores."""
    plan = [(s, t) for s, tablas in OBJETOS.items() for t in tablas]
    if objetos:
        pedidos = set(objetos)
        plan = [(s, t) for s, t in plan if f"{s}.{t}" in pedidos]
        desconocidos = pedidos - {f"{s}.{t}" for s, t in plan}
        if desconocidos:
            imprimir(f"  (No están en OBJETOS, se ignoran: {', '.join(sorted(desconocidos))})")

    client = None if dry_run else cliente()
    errores = []
    for schema, nombre in plan:
        objeto = f"{schema}.{nombre}"
        if not db.existe(objeto):
            imprimir(f"  – {objeto:<40} no existe en Postgres, se omite")
            continue
        try:
            df = preparar(db.leer(f'SELECT * FROM {schema}."{nombre}"'))
            if dry_run:
                imprimir(f"  · {objeto:<40} {len(df):>7} filas (dry-run)")
                continue
            filas = subir_df(client, schema, nombre, df)
            imprimir(f"  ✓ {objeto:<40} {filas:>7} filas en BigQuery")
        except Exception as e:  # sigue con las demás
            errores.append(objeto)
            imprimir(f"  ✗ {objeto}: {e}")
    return errores


def main(argv=None):
    ap = argparse.ArgumentParser(description="Copia a BigQuery lo que usa el dashboard.")
    ap.add_argument("--dry-run", action="store_true", help="Solo lee Postgres; no sube nada.")
    ap.add_argument("--solo", help="schema.tabla separadas por coma (ej. analitica.reportes)")
    a = ap.parse_args(argv)
    objetos = [x.strip() for x in a.solo.split(",") if x.strip()] if a.solo else None
    print(f"Subiendo a BigQuery (proyecto {GCP_PROJECT or '¿?'})…")
    errores = subir(objetos, dry_run=a.dry_run)
    if errores:
        print(f"❌ Terminó con errores en: {', '.join(errores)}")
        sys.exit(1)
    print("✅ Listo." if not a.dry_run else "✅ Dry-run listo (no se subió nada).")


if __name__ == "__main__":
    main()

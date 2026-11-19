"""Acceso a BigQuery: consultas con parámetros y cargas gratuitas (load jobs)."""
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

import pandas as pd
from google.cloud import bigquery

from .config import MAX_BYTES_CONSULTA, PROYECTO, tabla, tabla_id


@lru_cache(maxsize=1)
def cliente() -> bigquery.Client:
    return bigquery.Client(project=PROYECTO or None)


def p(nombre: str, tipo: str, valor) -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(nombre, tipo, valor)


def pa(nombre: str, tipo: str, valores) -> bigquery.ArrayQueryParameter:
    return bigquery.ArrayQueryParameter(nombre, tipo, list(valores))


def consultar(sql: str, params: list | None = None) -> pd.DataFrame:
    cfg = bigquery.QueryJobConfig(
        query_parameters=params or [], maximum_bytes_billed=MAX_BYTES_CONSULTA
    )
    return cliente().query(sql, job_config=cfg).to_dataframe()


def ejecutar(sql: str, params: list | None = None) -> int:
    cfg = bigquery.QueryJobConfig(
        query_parameters=params or [], maximum_bytes_billed=MAX_BYTES_CONSULTA
    )
    job = cliente().query(sql, job_config=cfg)
    job.result()
    return job.num_dml_affected_rows or 0


def _a_decimal(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return Decimal(str(round(float(v), 2)))


def cargar(df: pd.DataFrame, nombre_tabla: str, columnas_numeric: tuple = ()) -> None:
    """Agrega filas con un load job (gratis, a diferencia de streaming inserts)."""
    if df.empty:
        return
    df = df.copy()
    for c in columnas_numeric:
        if c in df.columns:
            df[c] = df[c].map(_a_decimal)
    destino = cliente().get_table(tabla_id(nombre_tabla))
    df = df.reindex(columns=[f.name for f in destino.schema])
    cfg = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND", schema=destino.schema
    )
    cliente().load_table_from_dataframe(df, destino, job_config=cfg).result()


def reemplazar(df: pd.DataFrame, nombre_tabla: str, columnas_numeric: tuple = ()) -> None:
    """Reemplaza TODO el contenido de la tabla (para fotografías: mantenimientos, inventario, stock)."""
    df = df.copy()
    for c in columnas_numeric:
        if c in df.columns:
            df[c] = df[c].map(_a_decimal)
    destino = cliente().get_table(tabla_id(nombre_tabla))
    columnas = [f.name for f in destino.schema]
    df = df.reindex(columns=columnas)
    cfg = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE", schema=destino.schema)
    cliente().load_table_from_dataframe(df, destino, job_config=cfg).result()


# ---------- lecturas frecuentes ----------

def propiedades(solo_activas: bool = True) -> pd.DataFrame:
    filtro = "WHERE activa" if solo_activas else ""
    return consultar(f"SELECT * FROM {tabla('propiedades')} {filtro} ORDER BY propiedad_id")


def categorias() -> pd.DataFrame:
    return consultar(f"SELECT * FROM {tabla('categorias')} ORDER BY tipo, grupo, categoria")


def reglas() -> pd.DataFrame:
    return consultar(f"SELECT * FROM {tabla('reglas_clasificacion')} ORDER BY prioridad")


def ids_existentes(ids: list[str]) -> set[str]:
    if not ids:
        return set()
    df = consultar(
        f"SELECT movimiento_id FROM {tabla('movimientos')} WHERE movimiento_id IN UNNEST(@ids)",
        [pa("ids", "STRING", ids)],
    )
    return set(df["movimiento_id"])

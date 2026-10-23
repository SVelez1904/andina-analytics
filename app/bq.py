"""Lectura de BigQuery para el dashboard.

- En Streamlit Cloud: usa la cuenta de servicio de Secrets ([gcp_service_account] y gcp_project).
- En tu computador: usa `gcloud auth application-default login` y GCP_PROJECT del .env.

Los datasets se llaman igual que los schemas de Postgres (public, analitica): ver analitica/subir_bigquery.py.
"""
import datetime as dt
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import streamlit as st

# Tope por query: si una query mal escrita fuera a escanear más, BigQuery la rechaza sin cobrar.
# No puede bajar de 10 MB (lo mínimo que se factura por query que lee una tabla). Hoy toda la data pesa < 1 MB.
MAX_BYTES_FACTURADOS = 100 * 1024 ** 2


def _secreto(clave):
    try:
        return st.secrets[clave]
    except Exception:  # sin secrets.toml o sin esa clave
        return None


@st.cache_resource(show_spinner=False)
def cliente():
    from google.cloud import bigquery

    from analitica.config import GCP_PROJECT

    proyecto = _secreto("gcp_project") or GCP_PROJECT or os.environ.get("GCP_PROJECT") or None
    info = _secreto("gcp_service_account")
    if info:
        from google.oauth2 import service_account

        cred = service_account.Credentials.from_service_account_info(dict(info))
        return bigquery.Client(credentials=cred, project=proyecto or cred.project_id)
    return bigquery.Client(project=proyecto)


def _parametro(nombre, valor):
    from google.cloud import bigquery

    if isinstance(valor, bool):
        tipo = "BOOL"
    elif isinstance(valor, (int, np.integer)):
        tipo = "INT64"
    elif isinstance(valor, (float, np.floating)):
        tipo = "FLOAT64"
    elif isinstance(valor, (dt.datetime, pd.Timestamp)):
        tipo = "TIMESTAMP"
    elif isinstance(valor, dt.date):
        tipo = "DATE"
    else:
        tipo, valor = "STRING", str(valor)
    return bigquery.ScalarQueryParameter(nombre, tipo, valor)


def _como_postgres(df):
    """BigQuery devuelve tipos 'nullable' de pandas (Int64, boolean, dbdate, arrays de numpy).
    Se pasan a los tipos que devolvía Postgres para que el resto del código funcione igual."""
    for col in df.columns:
        s = df[col]
        tipo = str(s.dtype)
        if tipo == "Int64":
            df[col] = s.astype("int64") if not s.isna().any() else s.to_numpy(dtype="float64", na_value=np.nan)
        elif tipo == "Float64":
            df[col] = s.to_numpy(dtype="float64", na_value=np.nan)
        elif tipo == "boolean":
            df[col] = s.astype(bool) if not s.isna().any() else s.astype(object).where(s.notna(), None)
        elif tipo in ("dbdate", "dbtime") or tipo.startswith("string"):
            df[col] = s.astype(object).where(s.notna(), None)
        elif tipo == "object":
            muestra = s.dropna()
            if not muestra.empty and isinstance(muestra.iloc[0], np.ndarray):   # ARRAY -> lista
                df[col] = s.map(lambda v: list(v) if isinstance(v, np.ndarray) else v)
    return df


def leer(sql, params=None):
    """SELECT -> DataFrame. Los parámetros se escriben @nombre en el SQL."""
    from google.cloud import bigquery

    cfg = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_FACTURADOS,
                                  query_parameters=[_parametro(k, v) for k, v in (params or {}).items()])
    df = cliente().query(sql, job_config=cfg).result().to_dataframe(create_bqstorage_client=False)
    return _como_postgres(df)


def estado(datasets):
    """(versión, tablas) solo con metadata: no es una query y no se cobra.
    versión = la última modificación de cualquier tabla (cambia con cada subir_bigquery);
    tablas = {'dataset.tabla', ...} que existen."""
    tablas = [t for ds in datasets for t in cliente().list_tables(ds)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        modificadas = list(ex.map(lambda t: cliente().get_table(t.reference).modified, tablas))
    version = max(modificadas).isoformat() if modificadas else ""
    return version, frozenset(f"{t.dataset_id}.{t.table_id}" for t in tablas)

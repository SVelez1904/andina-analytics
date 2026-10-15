"""Conexión a Postgres con el usuario de análisis (lee public, escribe solo en analitica)."""
from contextlib import contextmanager

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from .config import DB

_engine = None


def engine():
    global _engine
    if _engine is None:
        url = URL.create("postgresql+psycopg2", username=DB["user"], password=DB["password"],
                         host=DB["host"], port=DB["port"], database=DB["dbname"],
                         query={"sslmode": DB["sslmode"]} if DB["sslmode"] else {})
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def leer(sql, params=None):
    """Ejecuta un SELECT y devuelve un DataFrame."""
    with engine().connect() as con:
        return pd.read_sql(text(sql), con, params=params or {})


def existe(objeto):
    """True si la tabla o vista existe y es legible (ej. 'public.vw_reviews_actual')."""
    try:
        with engine().connect() as con:
            return con.execute(text("SELECT to_regclass(:o) IS NOT NULL"), {"o": objeto}).scalar()
    except Exception:
        return False


@contextmanager
def transaccion():
    """Bloque de escritura: todo o nada."""
    with engine().begin() as con:
        yield con


def ejecutar(con, sql, params=None):
    return con.execute(text(sql), params or {})

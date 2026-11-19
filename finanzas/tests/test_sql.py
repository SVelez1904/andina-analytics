"""Revisa la sintaxis de todos los .sql con el dialecto de BigQuery, sin conectarse a GCP.
(En GitHub Actions, el job `sql-dry-run` además los valida contra BigQuery real, gratis.)"""
from pathlib import Path

import pytest
import sqlglot

ARCHIVOS = sorted((Path(__file__).resolve().parents[1] / "sql").glob("*.sql"))


@pytest.mark.parametrize("archivo", ARCHIVOS, ids=lambda p: p.name)
def test_sql_valido(archivo):
    sentencias = [s for s in sqlglot.parse(archivo.read_text(), read="bigquery") if s is not None]
    assert sentencias, f"{archivo.name} no tiene sentencias"

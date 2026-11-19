"""Valida archivos .sql contra BigQuery real con dry-run (no ejecuta nada y no cuesta nada).
Reemplaza TU_PROYECTO por el proyecto indicado. Uso:
    python scripts/validar_sql_bigquery.py --proyecto mi-proyecto sql/03_vistas.sql
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from google.cloud import bigquery


def sentencias(texto: str) -> list[str]:
    sin_comentarios = re.sub(r"--[^\n]*", "", texto)
    return [s.strip() for s in sin_comentarios.split(";") if s.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proyecto", required=True)
    ap.add_argument("archivos", nargs="+")
    a = ap.parse_args()
    cliente = bigquery.Client(project=a.proyecto)
    errores = 0
    for archivo in a.archivos:
        for i, s in enumerate(sentencias(Path(archivo).read_text().replace("TU_PROYECTO", a.proyecto)), 1):
            try:
                cliente.query(s, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
                print(f"OK    {archivo} #{i}")
            except Exception as e:
                errores += 1
                print(f"ERROR {archivo} #{i}: {e}")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())

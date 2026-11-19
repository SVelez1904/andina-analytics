"""Guarda en BigQuery las sugerencias de clasificación que hizo Claude (tarea agendada).
NO confirma nada: los movimientos siguen PENDIENTES, con propiedad y categoría precargadas,
y una persona los confirma en la página Pendientes.

Uso:  python scripts/guardar_sugerencias.py salidas/sugerencias_AAAA-MM.csv
CSV:  movimiento_id,propiedad_id,categoria,confianza
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import bq  # noqa: E402
from lib.config import tabla  # noqa: E402


def main() -> None:
    df = pd.read_csv(sys.argv[1], dtype=str).fillna("")
    validas_p = set(bq.consultar(f"SELECT propiedad_id FROM {tabla('propiedades')}")["propiedad_id"])
    validas_c = set(bq.consultar(f"SELECT categoria FROM {tabla('categorias')}")["categoria"]) | {"__DESCARTAR__"}
    ok = df[df["categoria"].isin(validas_c) & (df["propiedad_id"].isin(validas_p) | (df["propiedad_id"] == ""))]
    descartadas = len(df) - len(ok)
    filas = [bigquery.StructQueryParameter(None,
                bigquery.ScalarQueryParameter("id", "STRING", r.movimiento_id),
                bigquery.ScalarQueryParameter("prop", "STRING", r.propiedad_id or None),
                bigquery.ScalarQueryParameter("cat", "STRING", r.categoria),
                bigquery.ScalarQueryParameter("conf", "FLOAT64", float(r.confianza or 0)))
             for r in ok.itertuples()]
    if not filas:
        print("No hay sugerencias válidas para guardar.")
        return
    n = bq.ejecutar(f"""
        UPDATE {tabla('movimientos')} m
        SET propiedad_id = IFNULL(f.prop, m.propiedad_id),
            categoria = IF(f.cat = '__DESCARTAR__', m.categoria, f.cat),
            confianza = f.conf,
            sugerencia = CONCAT('Claude: ', f.cat, ' / ', IFNULL(f.prop, '?'))
        FROM UNNEST(@filas) f
        WHERE m.movimiento_id = f.id AND m.estado = 'PENDIENTE'""",
        [bigquery.ArrayQueryParameter("filas", "STRUCT", filas)])
    print(f"{n} pendientes con sugerencia guardada (siguen PENDIENTES). {descartadas} filas ignoradas por códigos inválidos.")


if __name__ == "__main__":
    main()

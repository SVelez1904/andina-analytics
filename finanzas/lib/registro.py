"""Guardar movimientos nuevos (sin duplicados) y actualizar los pendientes."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pandas as pd

from . import bq
from .config import tabla

NUMERICOS = ("monto",)


def nueva_carga_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def guardar_movimientos(movs: pd.DataFrame, fuente: str, archivo: str, usuario: str,
                        carga_id: str, filas_leidas: int) -> dict:
    existentes = bq.ids_existentes(movs["movimiento_id"].tolist()) if not movs.empty else set()
    nuevos = movs[~movs["movimiento_id"].isin(existentes)].copy()
    nuevos["noches"] = nuevos["noches"].astype("Int64")
    nuevos["confianza"] = pd.to_numeric(nuevos["confianza"], errors="coerce")
    bq.cargar(nuevos, "movimientos", NUMERICOS)
    resumen = {
        "carga_id": carga_id, "fuente": fuente, "archivo": archivo,
        "filas_leidas": filas_leidas, "filas_nuevas": len(nuevos),
        "duplicados": len(movs) - len(nuevos),
        "pendientes": int((nuevos["estado"] == "PENDIENTE").sum()),
    }
    log = pd.DataFrame([{k: resumen[k] for k in ("carga_id", "fuente", "archivo", "filas_leidas", "filas_nuevas", "pendientes")}
                        | {"usuario": usuario, "creado_en": datetime.now(UTC)}])
    bq.cargar(log, "cargas")
    return resumen


def pendientes() -> pd.DataFrame:
    return bq.consultar(f"""SELECT movimiento_id, fecha, tipo, monto, moneda, descripcion,
            propiedad_id, categoria, sugerencia, confianza, fuente
        FROM {tabla('movimientos')} WHERE estado = 'PENDIENTE' ORDER BY fecha DESC LIMIT 500""")


def confirmar(filas: pd.DataFrame, usuario: str) -> int:
    """Marca como OK (o DESCARTADO) las filas revisadas por una persona, en una sola consulta."""
    if filas.empty:
        return 0
    datos = [{"id": r.movimiento_id, "prop": r.propiedad_id, "cat": r.categoria,
              "estado": "DESCARTADO" if r.descartar else "OK"} for r in filas.itertuples()]
    from google.cloud import bigquery
    param = bigquery.ArrayQueryParameter("filas", "STRUCT", [
        bigquery.StructQueryParameter(None,
            bigquery.ScalarQueryParameter("id", "STRING", d["id"]),
            bigquery.ScalarQueryParameter("prop", "STRING", d["prop"]),
            bigquery.ScalarQueryParameter("cat", "STRING", d["cat"]),
            bigquery.ScalarQueryParameter("estado", "STRING", d["estado"]))
        for d in datos])
    return bq.ejecutar(f"""
        UPDATE {tabla('movimientos')} m
        SET propiedad_id = f.prop, categoria = f.cat, estado = f.estado,
            clasificado_por = 'HUMANO', sugerencia = CONCAT(IFNULL(m.sugerencia, ''), ' | revisado por ', @u)
        FROM UNNEST(@filas) f
        WHERE m.movimiento_id = f.id""", [param, bq.p("u", "STRING", usuario)])


def crear_regla(patron: str, categoria: str, propiedad_id: str | None, prioridad: int = 50) -> None:
    bq.ejecutar(f"""INSERT INTO {tabla('reglas_clasificacion')} (patron, categoria, propiedad_id, prioridad, creado_en)
        VALUES (@p, @c, @prop, @prio, CURRENT_TIMESTAMP())""",
        [bq.p("p", "STRING", patron.upper()), bq.p("c", "STRING", categoria),
         bq.p("prop", "STRING", propiedad_id), bq.p("prio", "INT64", prioridad)])

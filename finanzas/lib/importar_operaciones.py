"""Carga de una planilla de operaciones a BigQuery. La usan la app (pestaña "Planillas de operaciones")
y el script `scripts/importar_operaciones.py` (carga masiva de la carpeta completa)."""
from __future__ import annotations

from datetime import date

from . import bq
from . import operaciones as op
from .config import tabla
from .registro import guardar_movimientos, nueva_carga_id


def _mapa() -> op.MapaPropiedades:
    return op.MapaPropiedades(bq.consultar(f"SELECT alias, propiedad_id FROM {tabla('alias_propiedades')}"))


def _reservas_por_propiedad(mes: date) -> dict:
    df = bq.consultar(f"""SELECT propiedad_id, COUNT(DISTINCT referencia) n FROM {tabla('movimientos')}
        WHERE categoria = 'reserva_airbnb' AND estado = 'OK' AND DATE_TRUNC(fecha, MONTH) = @m
        GROUP BY propiedad_id""", [bq.p("m", "DATE", mes)])
    return dict(zip(df["propiedad_id"], df["n"]))


def importar(contenido: bytes, nombre_archivo: str, usuario: str, propiedad_presupuesto: str | None = None) -> dict:
    """Detecta el tipo de planilla, la lee y la guarda. Devuelve un resumen para mostrar."""
    wb = op.abrir(contenido)
    tipo = op.detectar_tipo(wb)
    carga = nueva_carga_id()
    res: dict = {"tipo": tipo, "archivo": nombre_archivo}

    if tipo == "GASTOS":
        movs, info = op.parse_gastos(wb, _mapa(), carga, usuario)
        res |= info | guardar_movimientos(movs, "PLANILLA_GASTOS", nombre_archivo, usuario, carga, len(movs))
    elif tipo == "MANTENIMIENTO":
        mant, prev, info = op.parse_mantenimiento(wb, _mapa(), carga)
        bq.reemplazar(mant, "mantenimientos")
        bq.reemplazar(prev, "preventivas")
        res |= info
    elif tipo == "LIMPIEZA":
        aseos, info = op.parse_turnos(wb, _mapa(), carga)
        if len(aseos):
            ya = bq.consultar(f"SELECT limpieza_id FROM {tabla('limpiezas')} WHERE limpieza_id IN UNNEST(@ids)",
                              [bq.pa("ids", "STRING", aseos["limpieza_id"].tolist())])
            bq.cargar(aseos[~aseos["limpieza_id"].isin(set(ya["limpieza_id"]))], "limpiezas")
        equipo = bq.consultar(f"SELECT nombre, propiedades FROM {tabla('equipo_limpieza')} WHERE activa")
        mes = next((c.value.date().replace(day=1) for ws in wb.worksheets for row in ws.iter_rows(max_row=5)
                    for c in row if hasattr(c.value, "year")), date.today().replace(day=1))
        pagos, info_p = op.parse_pagos_limpieza(wb, equipo, _reservas_por_propiedad(mes), carga, usuario)
        g = guardar_movimientos(pagos, "PLANILLA_LIMPIEZA", nombre_archivo, usuario, carga, len(pagos))
        res |= info | {"pagos_limpieza": info_p, "pagos_nuevos": g["filas_nuevas"]}
    elif tipo == "INVENTARIO":
        inv, stk, info = op.parse_inventario(wb, _mapa(), carga)
        bq.reemplazar(inv, "inventario")
        bq.reemplazar(stk, "stock")
        res |= info
    elif tipo == "PRESUPUESTO":
        df, info = op.parse_presupuesto(wb, propiedad_presupuesto, nombre_archivo, carga)
        if len(df):
            ya = bq.consultar(f"SELECT inversion_id FROM {tabla('inversiones')} WHERE inversion_id = @i",
                              [bq.p("i", "STRING", df["inversion_id"].iloc[0])])
            if ya.empty:
                bq.cargar(df, "inversiones", ("monto_neto", "monto_total"))
        res |= info
    else:
        res["error"] = ("No reconozco esta planilla. Tipos aceptados: gastos operacionales, control de "
                        "mantenimiento, turnos de limpieza, inventario y presupuestos.")
    return res


def resumen_texto(r: dict) -> str:
    t = r["tipo"]
    if "error" in r:
        return r["error"]
    if t == "GASTOS":
        s = f"{r['filas_nuevas']} gastos nuevos ({r['duplicados']} ya existían). Total en la planilla: {r['total_clp']:,.0f} CLP."
        if r.get("fechas_estimadas"):
            s += f" {r['fechas_estimadas']} filas sin fecha quedaron con el día 1 del mes."
    elif t == "MANTENIMIENTO":
        s = f"{r['mantenimientos']} mantenimientos y {r['preventivas']} tareas preventivas actualizadas."
        if r.get("preventivas_sin_registro"):
            s += f" {r['preventivas_sin_registro']} preventivas no tienen fecha de última ejecución."
    elif t == "LIMPIEZA":
        s = f"{r['aseos']} aseos programados leídos; {r['pagos_nuevos']} pagos de limpieza nuevos."
    elif t == "INVENTARIO":
        s = f"{r['items']} ítems de inventario y {r['stock']} de stock actualizados; {r['para_comprar']} para comprar."
    elif t == "PRESUPUESTO":
        s = f"Presupuesto registrado: neto {r['neto']:,.0f}, total {r['total']:,.0f} CLP (estado PRESUPUESTO)."
    else:
        s = str(r)
    if r.get("sin_propiedad"):
        s += f" Sin propiedad reconocida: {', '.join(map(str, r['sin_propiedad']))} (agrégalas en alias_propiedades)."
    return s.replace(",", ".")

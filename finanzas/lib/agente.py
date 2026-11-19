"""Agente financiero: Claude decide QUÉ función usar; las funciones (SQL fijo, solo lectura)
calculan los números. Así las cifras siempre salen de BigQuery y el costo por pregunta es bajo."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import anthropic
import pandas as pd

from . import bq
from .config import MODELO_CLAUDE, tabla

SISTEMA = """Eres el analista financiero del negocio de arriendos de corto plazo de Leticia (Chile y Brasil).
Respondes en español, de forma breve y clara, a personas sin conocimientos técnicos.
Reglas:
- Usa SIEMPRE las funciones para obtener números. Nunca inventes ni estimes cifras.
- Nunca sumes montos de monedas distintas (CLP y BRL van por separado).
- Indica siempre el período y las propiedades a las que se refiere la respuesta.
- Formato de montos: CLP sin decimales con punto de miles (1.234.567 CLP); BRL con 2 decimales.
- Margen = resultado / ingresos. ROI = resultado / inversión inicial (solo si hay inversión registrada).
- "Gastos operativos" = limpieza, lavandería, amenities, servicios, internet, gastos comunes, software.
- Si faltan datos o hay movimientos pendientes de clasificar, dilo: pueden cambiar el resultado.
- Para mantenimiento, limpieza, inventario y alertas usa la función "operaciones".
Hoy es {hoy}."""

HERRAMIENTAS = [
    {
        "name": "listar_propiedades",
        "description": "Lista las propiedades con su código, nombre, ciudad, moneda, modelo de negocio (PROPIA, ARBITRAJE, COHOST, GESTION) e inversión inicial.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "pnl",
        "description": "Estado de resultados (ingresos, comisiones, gastos operativos, mantenimiento, gastos fijos, resultado, margen, noches, ADR, ocupación, ROI) por propiedad, agrupado por mes o por año, entre dos fechas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "desde": {"type": "string", "description": "AAAA-MM-DD, inclusive"},
                "hasta": {"type": "string", "description": "AAAA-MM-DD, inclusive"},
                "agrupar_por": {"type": "string", "enum": ["mes", "anio"]},
                "propiedad_id": {"type": "string", "description": "Opcional. Código de una propiedad."},
            },
            "required": ["desde", "hasta", "agrupar_por"],
        },
    },
    {
        "name": "ranking_rentabilidad",
        "description": "Ordena las propiedades por resultado neto y margen en un período. Una lista por moneda.",
        "input_schema": {
            "type": "object",
            "properties": {
                "desde": {"type": "string"}, "hasta": {"type": "string"},
            },
            "required": ["desde", "hasta"],
        },
    },
    {
        "name": "gastos_por_categoria",
        "description": "Total de gastos por categoría (y grupo) en un período, opcionalmente de una propiedad.",
        "input_schema": {
            "type": "object",
            "properties": {
                "desde": {"type": "string"}, "hasta": {"type": "string"},
                "propiedad_id": {"type": "string"},
            },
            "required": ["desde", "hasta"],
        },
    },
    {
        "name": "detalle_movimientos",
        "description": "Lista movimientos individuales (máx. 50) para explicar una cifra: fecha, descripción, categoría, monto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "desde": {"type": "string"}, "hasta": {"type": "string"},
                "propiedad_id": {"type": "string"}, "categoria": {"type": "string"},
                "tipo": {"type": "string", "enum": ["INGRESO", "GASTO"]},
            },
            "required": ["desde", "hasta"],
        },
    },
    {
        "name": "operaciones",
        "description": ("Indicadores operativos. tema='mensual': por propiedad y mes, cantidad de mantenimientos, "
                        "urgentes, correctivos, daños de huésped, noches bloqueadas, días para resolver, aseos "
                        "programados y gasto en mantenimiento/limpieza/insumos. tema='alertas': preventivas vencidas, "
                        "stock para comprar, inventario a reparar y mantenciones abiertas. tema='mantenimientos': "
                        "detalle de trabajos (qué, quién, prioridad). tema='inventario': valor e ítems por propiedad."),
        "input_schema": {
            "type": "object",
            "properties": {
                "tema": {"type": "string", "enum": ["mensual", "alertas", "mantenimientos", "inventario"]},
                "desde": {"type": "string"}, "hasta": {"type": "string"},
                "propiedad_id": {"type": "string"},
            },
            "required": ["tema"],
        },
    },
    {
        "name": "pendientes",
        "description": "Cuántos movimientos faltan por clasificar y por cuánto dinero, por moneda.",
        "input_schema": {"type": "object", "properties": {}},
    },
]
# Cache del prompt de sistema + herramientas: abarata las preguntas seguidas
HERRAMIENTAS[-1]["cache_control"] = {"type": "ephemeral"}


def _filtro(permitidas: list[str] | None, propiedad_id: str | None, params: list) -> str:
    sql = ""
    if permitidas is not None:
        sql += " AND propiedad_id IN UNNEST(@permitidas)"
        params.append(bq.pa("permitidas", "STRING", permitidas))
    if propiedad_id:
        sql += " AND propiedad_id = @prop"
        params.append(bq.p("prop", "STRING", propiedad_id))
    return sql


def _fechas(args: dict, params: list) -> None:
    params += [bq.p("desde", "DATE", date.fromisoformat(args["desde"])),
               bq.p("hasta", "DATE", date.fromisoformat(args["hasta"]))]


def _a_json(df: pd.DataFrame) -> str:
    if df.empty:
        return "Sin datos para ese filtro."
    df = df.map(lambda v: float(v) if isinstance(v, Decimal) else v)  # NUMERIC llega como Decimal
    return df.to_json(orient="records", date_format="iso", force_ascii=False, default_handler=str)


def ejecutar_herramienta(nombre: str, args: dict, permitidas: list[str] | None) -> str:
    params: list = []
    if nombre == "listar_propiedades":
        f = _filtro(permitidas, None, params)
        df = bq.consultar(f"""SELECT propiedad_id, nombre, ciudad, moneda, modelo_negocio, comision_pct,
            inversion_inicial, arriendo_mensual FROM {tabla('propiedades')} WHERE activa {f}""", params)
    elif nombre == "pnl":
        _fechas(args, params)
        f = _filtro(permitidas, args.get("propiedad_id"), params)
        if args["agrupar_por"] == "anio":
            df = bq.consultar(f"""SELECT * FROM {tabla('pnl_anual')}
                WHERE anio BETWEEN EXTRACT(YEAR FROM @desde) AND EXTRACT(YEAR FROM @hasta) {f}
                ORDER BY propiedad_id, anio""", params)
        else:
            df = bq.consultar(f"""SELECT * FROM {tabla('pnl_mensual')}
                WHERE mes BETWEEN DATE_TRUNC(@desde, MONTH) AND @hasta {f}
                ORDER BY propiedad_id, mes""", params)
    elif nombre == "ranking_rentabilidad":
        _fechas(args, params)
        f = _filtro(permitidas, None, params)
        df = bq.consultar(f"""SELECT propiedad_id, propiedad, modelo_negocio, moneda,
                SUM(ingresos) ingresos, SUM(gastos_totales) gastos, SUM(resultado) resultado,
                SAFE_DIVIDE(SUM(resultado), SUM(ingresos)) margen
            FROM {tabla('pnl_mensual')}
            WHERE mes BETWEEN DATE_TRUNC(@desde, MONTH) AND @hasta AND propiedad_id != 'GENERAL' {f}
            GROUP BY 1, 2, 3, 4 ORDER BY moneda, resultado DESC""", params)
    elif nombre == "gastos_por_categoria":
        _fechas(args, params)
        f = _filtro(permitidas, args.get("propiedad_id"), params)
        df = bq.consultar(f"""SELECT moneda, grupo, categoria, SUM(monto) total, COUNT(*) movimientos
            FROM {tabla('v_movimientos')}
            WHERE tipo = 'GASTO' AND fecha BETWEEN @desde AND @hasta {f}
            GROUP BY 1, 2, 3 ORDER BY moneda, total DESC""", params)
    elif nombre == "detalle_movimientos":
        _fechas(args, params)
        f = _filtro(permitidas, args.get("propiedad_id"), params)
        if args.get("categoria"):
            f += " AND categoria = @cat"
            params.append(bq.p("cat", "STRING", args["categoria"]))
        if args.get("tipo"):
            f += " AND tipo = @tipo"
            params.append(bq.p("tipo", "STRING", args["tipo"]))
        df = bq.consultar(f"""SELECT fecha, propiedad_id, tipo, categoria, monto, moneda, descripcion
            FROM {tabla('v_movimientos')} WHERE fecha BETWEEN @desde AND @hasta {f}
            ORDER BY monto DESC LIMIT 50""", params)
    elif nombre == "operaciones":
        tema = args["tema"]
        desde = date.fromisoformat(args.get("desde") or "2000-01-01")
        hasta = date.fromisoformat(args.get("hasta") or "2100-01-01")
        params += [bq.p("desde", "DATE", desde), bq.p("hasta", "DATE", hasta)]
        f = _filtro(permitidas, args.get("propiedad_id"), params)
        if tema == "mensual":
            df = bq.consultar(f"""SELECT * FROM {tabla('operaciones_mensual')}
                WHERE mes BETWEEN DATE_TRUNC(@desde, MONTH) AND @hasta {f} ORDER BY mes, propiedad_id""", params)
        elif tema == "alertas":
            if permitidas is not None:
                f = f.replace("AND propiedad_id IN", "AND IFNULL(propiedad_id, '') IN")
            df = bq.consultar(f"""SELECT tipo, propiedad_id, detalle, estado, fecha
                FROM {tabla('alertas_operacion')} WHERE TRUE {f} ORDER BY tipo LIMIT 100""",
                [x for x in params if x.name not in ("desde", "hasta")])
        elif tema == "mantenimientos":
            df = bq.consultar(f"""SELECT fecha_reporte, propiedad_id, categoria, descripcion, tipo, prioridad,
                    realizado_por, estado, dias_resolver, noches_bloqueadas, cobrable_huesped
                FROM {tabla('mantenimientos')} WHERE fecha_reporte BETWEEN @desde AND @hasta {f}
                ORDER BY fecha_reporte DESC LIMIT 50""", params)
        else:
            df = bq.consultar(f"""SELECT propiedad_id, COUNT(*) items, SUM(cantidad) unidades,
                    SUM(valor_total) valor_registrado, COUNTIF(valor_total IS NULL) items_sin_valor
                FROM {tabla('inventario')} WHERE TRUE {f} GROUP BY propiedad_id ORDER BY propiedad_id""",
                [x for x in params if x.name not in ("desde", "hasta")])
    elif nombre == "pendientes":
        if permitidas is not None:
            return "Esta información es solo para el equipo administrador."
        df = bq.consultar(f"""SELECT moneda, COUNT(*) movimientos, SUM(monto) monto
            FROM {tabla('movimientos')} WHERE estado = 'PENDIENTE' GROUP BY moneda""")
    else:
        return f"Función desconocida: {nombre}"
    return _a_json(df)


def responder(historial: list[dict], permitidas: list[str] | None,
              cliente: anthropic.Anthropic | None = None, max_pasos: int = 6) -> tuple[str, list[dict]]:
    """Ejecuta el ciclo pregunta → funciones → respuesta. Devuelve (texto, historial actualizado)."""
    cliente = cliente or anthropic.Anthropic()
    sistema = [{"type": "text", "text": SISTEMA.format(hoy=date.today().isoformat()),
                "cache_control": {"type": "ephemeral"}}]
    mensajes = list(historial)
    for _ in range(max_pasos):
        resp = cliente.messages.create(model=MODELO_CLAUDE, max_tokens=1500, system=sistema,
                                       tools=HERRAMIENTAS, messages=mensajes)
        mensajes.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
        if resp.stop_reason != "tool_use":
            texto = "".join(b.text for b in resp.content if b.type == "text")
            return texto, mensajes
        resultados = []
        for b in resp.content:
            if b.type == "tool_use":
                try:
                    salida = ejecutar_herramienta(b.name, b.input, permitidas)
                except Exception as e:  # el modelo ve el error y puede corregir los parámetros
                    salida = f"Error: {e}"
                resultados.append({"type": "tool_result", "tool_use_id": b.id, "content": salida[:20000]})
        mensajes.append({"role": "user", "content": resultados})
    return "No pude completar el análisis en pocos pasos. Intenta una pregunta más específica.", mensajes

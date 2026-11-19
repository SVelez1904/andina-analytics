"""Lectura de las planillas de la carpeta 3. OPERATIONS.

Cada función recibe un workbook de openpyxl y devuelve DataFrames listos para BigQuery.
El tipo de planilla se detecta por los nombres de sus hojas, así no importa cómo se llame el archivo.

| Planilla                         | Destino en BigQuery                                  |
|----------------------------------|------------------------------------------------------|
| Planilha_GASTOS_OPERACIONAIS     | movimientos (gastos)                                 |
| Control_Mantenimiento_Airbnb     | mantenimientos, preventivas (fotografía completa)    |
| TURNOS LIMPEZA                   | limpiezas (aseos programados) + movimientos (pagos)  |
| INVENTARIO_DEPTOS                | inventario, stock (fotografía completa)              |
| Presupuesto de trabajo ...       | inversiones                                          |
"""
from __future__ import annotations

import io
from datetime import UTC, date, datetime

import openpyxl
import pandas as pd

from .parsers import COLUMNAS_MOV, hacer_id, normalizar

# ----------------------------------------------------------------- utilidades

# Nombres de las planillas que no son una propiedad → gastos generales del negocio
ALIAS_GENERAL = {"general", "varios deptos", "oficina", "bodegas", "leticia / admin", "admin", "andina"}

CATEGORIA_GASTOS = {
    "mantencion (mano de obra)": "mantenimiento",
    "mantencion": "mantenimiento",
    "lavanderia": "lavanderia",
    "insumos": "amenities",
    "otros": "otros_gastos",
}


def abrir(contenido: bytes) -> openpyxl.Workbook:
    return openpyxl.load_workbook(io.BytesIO(contenido), data_only=True)


def detectar_tipo(wb: openpyxl.Workbook) -> str:
    hojas = {normalizar(h) for h in wb.sheetnames}
    if "ene" in hojas and any(h.startswith("resumen") for h in hojas):
        return "GASTOS"
    if {"registro", "preventivas"} <= hojas:
        return "MANTENIMIENTO"
    if "enxoval" in hojas or "stock amenities" in hojas:
        return "INVENTARIO"
    if "limpeza meninas" in hojas or _contiene(wb, "limpieza semana"):
        return "LIMPIEZA"
    if _contiene(wb, "presupuesto") or (_contiene(wb, "neto") and _contiene(wb, "total")):
        return "PRESUPUESTO"
    return "DESCONOCIDO"


def _contiene(wb: openpyxl.Workbook, texto: str, filas: int = 40) -> bool:
    for ws in wb.worksheets:
        for row in ws.iter_rows(max_row=filas, values_only=True):
            if any(v is not None and texto in normalizar(v) for v in row):
                return True
    return False


class MapaPropiedades:
    """Traduce 'Encina 911', 'ENCINA 911', 'Pucón 403 ' → propiedad_id usando la tabla alias_propiedades."""

    def __init__(self, alias: pd.DataFrame):
        self._mapa = {normalizar(a): p for a, p in zip(alias["alias"], alias["propiedad_id"])}

    def __call__(self, nombre) -> str | None:
        if nombre is None or str(nombre).strip() == "":
            return None
        n = normalizar(nombre)
        if n in ALIAS_GENERAL:
            return "GENERAL"
        return self._mapa.get(n)


def _fecha(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if v is None or str(v).strip() == "":
        return None
    try:
        return pd.to_datetime(str(v), dayfirst=True).date()
    except (ValueError, TypeError):
        return None


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _filas_tabla(ws, encabezado_clave: str, max_buscar: int = 15):
    """Encuentra la fila de encabezados (la que contiene `encabezado_clave`) y entrega
    (encabezados normalizados, filas de datos como dict)."""
    for i, row in enumerate(ws.iter_rows(max_row=max_buscar, values_only=True), start=1):
        if any(v is not None and normalizar(v) == encabezado_clave for v in row):
            enc = [normalizar(v) if v is not None else f"_col{j}" for j, v in enumerate(row)]
            datos = []
            for r in ws.iter_rows(min_row=i + 1, values_only=True):
                d = dict(zip(enc, r))
                if any(v is not None and str(v).strip() != "" for v in r):
                    datos.append(d)
            return enc, datos
    return [], []


def _ahora():
    return datetime.now(UTC)


def _mov(**kw) -> dict:
    base = {c: None for c in COLUMNAS_MOV}
    base.update(creado_en=_ahora())
    base.update(kw)
    return base


# ----------------------------------------------------------------- 1. Gastos operacionales

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _anio_hoja(ws) -> int:
    """Año del título de la pestaña ('GASTOS OPERACIONALES · ENERO 2026')."""
    import re
    for row in ws.iter_rows(max_row=3, values_only=True):
        for v in row:
            m = re.search(r"(20\d{2})", str(v or ""))
            if m:
                return int(m.group(1))
    return date.today().year


def parse_gastos(wb, mapa: MapaPropiedades, carga_id: str, usuario: str) -> tuple[pd.DataFrame, dict]:
    filas, sin_propiedad, sin_pagar, vistos, fechas_estimadas = [], set(), 0, {}, 0
    for hoja in wb.sheetnames:
        if normalizar(hoja) not in MESES:
            continue
        ws = wb[hoja]
        anio = _anio_hoja(ws)
        mes_hoja = date(anio, MESES.index(normalizar(hoja)) + 1, 1)
        _, datos = _filas_tabla(ws, "fecha")
        for d in datos:
            fecha, valor = _fecha(d.get("fecha")), _num(d.get("valor (clp)") or d.get("valor"))
            if not valor:
                continue
            estimada = fecha is None
            fecha = fecha or mes_hoja  # fila sin fecha: se asume el día 1 del mes de la pestaña
            depto = d.get("depto")
            prop = mapa(depto)
            if prop is None:
                sin_propiedad.add(str(depto).strip())
            cat = CATEGORIA_GASTOS.get(normalizar(d.get("categoria") or ""), "otros_gastos")
            desc = str(d.get("descripcion del gasto") or "").strip()
            pagado = normalizar(d.get("pagado?") or "")
            if pagado == "no":
                sin_pagar += 1
            clave = (fecha, str(depto), desc, valor)
            vistos[clave] = vistos.get(clave, 0) + 1
            obs = d.get("observaciones")
            if estimada:
                obs = f"{obs or ''} [fecha estimada]".strip()
                fechas_estimadas += 1
            filas.append(_mov(
                movimiento_id=hacer_id("PLANILLA_GASTOS", *clave, vistos[clave]),
                fecha=fecha, propiedad_id=prop, tipo="GASTO", categoria=cat, monto=abs(valor),
                moneda="CLP", descripcion=f"{desc} ({depto})" + (f" — {obs}" if obs else ""),
                referencia="SIN PAGAR" if pagado == "no" else None,
                fuente="PLANILLA_GASTOS", estado="OK" if prop else "PENDIENTE",
                clasificado_por="PLANILLA", carga_id=carga_id, creado_por=usuario))
    df = pd.DataFrame(filas, columns=COLUMNAS_MOV)
    return df, {"gastos": len(df), "total_clp": float(df["monto"].sum()) if len(df) else 0.0,
                "sin_propiedad": sorted(sin_propiedad), "sin_pagar": sin_pagar,
                "fechas_estimadas": fechas_estimadas}


# ----------------------------------------------------------------- 2. Mantenimiento

def _si(v) -> bool | None:
    n = normalizar(v or "")
    return True if n in ("si", "sí", "yes") else False if n == "no" else None


def parse_mantenimiento(wb, mapa: MapaPropiedades, carga_id: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    _, datos = _filas_tabla(wb["Registro"], "id")
    regs = []
    for d in datos:
        fecha = _fecha(d.get("fecha del reporte"))
        if not fecha and not d.get("descripcion del problema / trabajo"):
            continue
        regs.append({
            "mantenimiento_id": d.get("id") or f"MT-SINID-{hacer_id(fecha, d.get('propiedad'), d.get('descripcion del problema / trabajo'))[:8]}",
            "fecha_reporte": fecha,
            "propiedad_id": mapa(d.get("propiedad")),
            "propiedad_planilla": d.get("propiedad"),
            "ambiente": d.get("ambiente"),
            "categoria": d.get("categoria"),
            "item": (str(d.get("item / equipo") or "").strip() or None),
            "descripcion": (str(d.get("descripcion del problema / trabajo") or "").strip() or None),
            "tipo": d.get("tipo"),
            "prioridad": d.get("prioridad"),
            "origen": d.get("origen del reporte"),
            "realizado_por": (str(d.get("realizado por") or "").strip() or None),
            "fecha_ejecucion": _fecha(d.get("fecha de ejecucion")),
            "estado": d.get("estado"),
            "dias_resolver": _num(d.get("dias hasta resolver")),
            "costo_registrado": _num(d.get("costo total")),
            "bloqueo_reservas": _si(d.get("bloqueo reservas?")),
            "noches_bloqueadas": _num(d.get("noches bloqueadas")),
            "cobrable_huesped": _si(d.get("cobrable al huesped?")),
            "codigo_reserva": d.get("codigo de reserva / huesped"),
            "carga_id": carga_id, "actualizado_en": _ahora(),
        })
    mant = pd.DataFrame(regs)

    _, datos_p = _filas_tabla(wb["Preventivas"], "tarea preventiva")
    prev = []
    for d in datos_p:
        if not d.get("propiedad") or not d.get("tarea preventiva"):
            continue
        prev.append({
            "propiedad_id": mapa(d.get("propiedad")), "propiedad_planilla": d.get("propiedad"),
            "tarea": d.get("tarea preventiva"), "categoria": d.get("categoria"),
            "frecuencia_dias": _num(d.get("frecuencia (dias)")),
            "ultima_ejecucion": _fecha(d.get("ultima ejecucion")),
            "proxima_fecha": _fecha(d.get("proxima fecha")),
            "estado": d.get("estado"), "responsable": d.get("responsable habitual"),
            "carga_id": carga_id, "actualizado_en": _ahora(),
        })
    prev = pd.DataFrame(prev)
    sin = sorted({str(x) for x in mant.get("propiedad_planilla", pd.Series(dtype=str))[mant.get("propiedad_id", pd.Series(dtype=str)).isna()]} if len(mant) else set())
    return mant, prev, {"mantenimientos": len(mant), "preventivas": len(prev), "sin_propiedad": sin,
                        "preventivas_sin_registro": int((prev["estado"].astype(str).str.upper() == "SIN REGISTRO").sum()) if len(prev) else 0}


# ----------------------------------------------------------------- 3. Limpieza

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def parse_turnos(wb, mapa: MapaPropiedades, carga_id: str) -> tuple[pd.DataFrame, dict]:
    """Hoja de turnos semanales: una 'x' = un aseo programado ese día en ese depto."""
    ws = wb.worksheets[0]
    filas_ws = list(ws.iter_rows(values_only=True))
    aseos, fechas_col = [], {}
    for i, row in enumerate(filas_ws):
        norm = [normalizar(v) if v is not None else "" for v in row]
        if "depto" in norm and "lunes" in norm:
            fechas = filas_ws[i - 1] if i > 0 else ()
            fechas_col = {j: _fecha(fechas[j]) for j, v in enumerate(norm) if v in DIAS and j < len(fechas)}
            col_depto = norm.index("depto")
            continue
        if not fechas_col:
            continue
        depto = row[col_depto] if col_depto < len(row) else None
        if not depto or normalizar(depto) in ("depto", ""):
            continue
        for j, f in fechas_col.items():
            if j < len(row) and row[j] is not None and normalizar(row[j]) in ("x", "1", "si"):
                aseos.append({"fecha": f, "propiedad_id": mapa(depto), "propiedad_planilla": str(depto).strip(),
                              "carga_id": carga_id, "creado_en": _ahora()})
    df = pd.DataFrame(aseos)
    if len(df):
        df["limpieza_id"] = [hacer_id("ASEO", f, p) for f, p in zip(df["fecha"], df["propiedad_planilla"])]
    return df, {"aseos": len(df), "sin_propiedad": sorted(set(df.loc[df["propiedad_id"].isna(), "propiedad_planilla"])) if len(df) else []}


def parse_pagos_limpieza(wb, equipo: pd.DataFrame, reservas_mes: dict, carga_id: str, usuario: str) -> tuple[pd.DataFrame, dict]:
    """Hoja 'limpeza meninas': N° de aseos y valor a pagar por persona en un mes.
    `equipo` (tabla equipo_limpieza) dice qué propiedades atiende cada persona. Si atiende varias,
    el pago se reparte en proporción a las reservas del mes (`reservas_mes`: propiedad_id → n)."""
    if "limpeza meninas" not in [normalizar(h) for h in wb.sheetnames]:
        return pd.DataFrame(columns=COLUMNAS_MOV), {"pagos": 0}
    ws = wb[[h for h in wb.sheetnames if normalizar(h) == "limpeza meninas"][0]]
    mes, filas, sin_equipo = None, [], []
    personas = {normalizar(n).split()[0]: (n, list(p) if p is not None else []) for n, p in zip(equipo["nombre"], equipo["propiedades"])}
    for row in ws.iter_rows(values_only=True):
        vals = [v for v in row if v is not None]
        for v in vals:
            if isinstance(v, datetime) and mes is None:
                mes = v.date().replace(day=1)
        if normalizar(" ".join(map(str, vals))).startswith("gastos de"):
            break  # lo que sigue es un resumen de la planilla de gastos: no se importa
        textos = [v for v in vals if isinstance(v, str)]
        nums = [v for v in vals if isinstance(v, (int, float))]
        if not textos or len(nums) < 2:
            continue
        nombre_txt = next((t for t in textos if normalizar(t).split()[0] in personas), None)
        if not nombre_txt:
            if not any(k in normalizar(" ".join(textos)) for k in ("aseos", "valor")):
                sin_equipo.append(" ".join(textos))
            continue
        n_aseos, monto = nums[-2], nums[-1]
        nombre, props = personas[normalizar(nombre_txt).split()[0]]
        props = [p for p in props if p] or ["GENERAL"]
        pesos = [reservas_mes.get(p, 0) for p in props]
        if sum(pesos) == 0:
            pesos = [1] * len(props)
        fecha = mes or date.today().replace(day=1)
        for p, w in zip(props, pesos):
            parte = round(monto * w / sum(pesos))
            if parte <= 0:
                continue
            filas.append(_mov(
                movimiento_id=hacer_id("PAGO_LIMPIEZA", fecha, nombre, p), fecha=fecha, propiedad_id=p,
                tipo="GASTO", categoria="limpieza", monto=float(parte), moneda="CLP",
                descripcion=f"Aseos {nombre} {fecha:%m/%Y}: {int(n_aseos)} aseos, total {monto:,.0f}".replace(",", ".")
                + (f" (prorrateo {w}/{sum(pesos)} reservas)" if len(props) > 1 else ""),
                fuente="PLANILLA_LIMPIEZA", estado="OK", clasificado_por="PRORRATEO" if len(props) > 1 else "PLANILLA",
                carga_id=carga_id, creado_por=usuario))
    df = pd.DataFrame(filas, columns=COLUMNAS_MOV)
    return df, {"pagos": len(df), "mes": mes, "total_clp": float(df["monto"].sum()) if len(df) else 0.0,
                "personas_no_registradas": sin_equipo}


# ----------------------------------------------------------------- 4. Inventario

def parse_inventario(wb, mapa: MapaPropiedades, carga_id: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    items, stock = [], []
    for hoja in wb.sheetnames:
        h = normalizar(hoja)
        ws = wb[hoja]
        if h in ("resumen", "listas"):
            continue
        if h == "enxoval":
            _, datos = _filas_tabla(ws, "tipo")
            for d in datos:
                if not d.get("tipo"):
                    continue
                stock.append({"tipo_stock": "ROPA_CAMA_BANO", "ubicacion": "Todas",
                              "item": " ".join(str(x) for x in (d.get("tipo"), d.get("tamano"), d.get("color")) if x),
                              "cantidad": _num(d.get("total")), "stock_minimo": _num(d.get("stock minimo")),
                              "estado": d.get("estado"), "danadas": _num(d.get("danadas / baja"))})
        elif h.startswith("stock"):
            tipo = "AMENITIES" if "amenities" in h else "LIMPIEZA"
            _, datos = _filas_tabla(ws, "item")
            for d in datos:
                if not d.get("item"):
                    continue
                stock.append({"tipo_stock": tipo, "ubicacion": d.get("bodega / ubicacion"),
                              "item": " ".join(str(x) for x in (d.get("item"), d.get("tamano / unidad")) if x),
                              "cantidad": _num(d.get("cantidad actual")), "stock_minimo": _num(d.get("stock minimo")),
                              "estado": d.get("estado"), "danadas": None})
        else:
            prop = mapa(hoja)
            _, datos = _filas_tabla(ws, "ambiente")
            for d in datos:
                if not d.get("item"):
                    continue
                items.append({"propiedad_id": prop, "propiedad_planilla": hoja, "ambiente": d.get("ambiente"),
                              "categoria": d.get("categoria"), "item": d.get("item"),
                              "detalle": d.get("detalle (color, tamano, marca)"),
                              "cantidad": _num(d.get("cantidad")), "valor_unitario": _num(d.get("valor unit. (clp)")),
                              "valor_total": _num(d.get("valor total")), "estado": d.get("estado"),
                              "fecha_compra": _fecha(d.get("fecha compra"))})
    inv, stk = pd.DataFrame(items), pd.DataFrame(stock)
    for df in (inv, stk):
        if len(df):
            df["carga_id"], df["actualizado_en"] = carga_id, _ahora()
    return inv, stk, {
        "items": len(inv), "stock": len(stk),
        "sin_propiedad": sorted(set(inv.loc[inv["propiedad_id"].isna(), "propiedad_planilla"])) if len(inv) else [],
        "para_comprar": int((stk["estado"].astype(str).str.upper() == "COMPRAR").sum()) if len(stk) else 0,
    }


# ----------------------------------------------------------------- 5. Presupuestos / reformas

def parse_presupuesto(wb, propiedad_id: str | None, nombre_archivo: str, carga_id: str) -> tuple[pd.DataFrame, dict]:
    """Toma el 'Total' (con IVA) y el 'Neto' del presupuesto. Queda como PRESUPUESTO hasta que
    se marque EJECUTADO; solo lo ejecutado suma a la inversión para el ROI."""
    total = neto = None
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            vals = [v for v in row if v is not None]
            for k, v in enumerate(vals):
                n = normalizar(v) if isinstance(v, str) else ""
                siguiente = next((x for x in vals[k + 1:] if isinstance(x, (int, float))), None)
                if n == "total" and siguiente is not None:
                    total = siguiente
                elif n == "neto" and siguiente is not None:
                    neto = siguiente
    if total is None and neto is None:
        return pd.DataFrame(), {"error": "No encontré las filas 'Neto' o 'Total' en el presupuesto."}
    df = pd.DataFrame([{
        "inversion_id": hacer_id("PRESUPUESTO", nombre_archivo, total or neto),
        "fecha": date.today(), "propiedad_id": propiedad_id, "concepto": nombre_archivo.rsplit(".", 1)[0],
        "tipo": "REFORMA", "monto_neto": neto, "monto_total": total or neto, "moneda": "CLP",
        "estado": "PRESUPUESTO", "carga_id": carga_id, "creado_en": _ahora()}])
    return df, {"neto": neto, "total": total}

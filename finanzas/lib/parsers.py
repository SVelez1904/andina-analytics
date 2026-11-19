"""Lectura de archivos: CSV de transacciones de Airbnb y cartolas bancarias (CSV/Excel).

Todo devuelve un DataFrame con las columnas de la tabla `movimientos`.
Los formatos de Airbnb y de cada banco cambian con el tiempo: si un archivo no se lee,
agrega el nombre de la columna nueva a las listas de ALIAS de este archivo.
"""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from datetime import UTC, datetime

import pandas as pd

COLUMNAS_MOV = [
    "movimiento_id", "fecha", "propiedad_id", "tipo", "categoria", "monto", "moneda",
    "descripcion", "referencia", "noches", "fuente", "estado", "clasificado_por",
    "confianza", "sugerencia", "archivo_url", "carga_id", "creado_por", "creado_en",
]


# ---------------------------------------------------------------- utilidades

def normalizar(texto) -> str:
    """minúsculas, sin tildes ni espacios extra: 'Código de confirmación' -> 'codigo de confirmacion'."""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def parse_monto(valor) -> float | None:
    """Acepta 1.234.567 | 1,234.56 | 1.234,56 | $ -12.000 | (12.000) | 1234."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip()
    if not s:
        return None
    negativo = "-" in s or (s.startswith("(") and s.endswith(")"))
    s = re.sub(r"[^\d,.]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        # el último separador es el decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        partes = s.split(",")
        s = s.replace(",", ".") if len(partes) == 2 and len(partes[1]) <= 2 else s.replace(",", "")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3):
        s = s.replace(".", "")  # 1.234.567 o 12.000 (miles en CLP)
    v = float(s)
    return -v if negativo else v


_FORMATOS_FECHA = ["%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%m/%d/%y", "%d.%m.%Y"]


def parse_fechas(serie: pd.Series) -> pd.Series:
    """Elige el formato que interpreta TODA la columna (evita confundir 03/04 con 04/03)."""
    valores = serie.dropna().astype(str).str.strip().str.slice(0, 10)
    valores = valores[valores != ""]
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie.dt.date
    for fmt in _FORMATOS_FECHA:
        convertido = pd.to_datetime(valores, format=fmt, errors="coerce")
        if len(valores) and convertido.notna().all():
            return pd.to_datetime(serie.astype(str).str.strip().str.slice(0, 10), format=fmt, errors="coerce").dt.date
    return pd.to_datetime(serie, errors="coerce", dayfirst=True).dt.date


def leer_tabla(contenido: bytes, nombre_archivo: str, palabra_encabezado: str | None = None) -> pd.DataFrame:
    """Lee CSV o Excel. Si `palabra_encabezado` viene, busca la fila de títulos (las cartolas
    suelen traer filas con el nombre del banco y el RUT antes de la tabla)."""
    nombre = nombre_archivo.lower()
    if nombre.endswith((".xlsx", ".xls")):
        crudo = pd.read_excel(io.BytesIO(contenido), header=None, dtype=str)
    else:
        texto = None
        for enc in ("utf-8-sig", "latin-1"):
            try:
                texto = contenido.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        crudo = pd.read_csv(io.StringIO(texto), header=None, dtype=str, sep=None, engine="python")
    fila = 0
    if palabra_encabezado:
        for i in range(min(len(crudo), 30)):
            if any(palabra_encabezado in normalizar(v) for v in crudo.iloc[i].fillna("")):
                fila = i
                break
    df = crudo.iloc[fila + 1:].copy()
    df.columns = [str(c).strip() for c in crudo.iloc[fila].fillna("")]
    df = df.dropna(how="all")
    return df.reset_index(drop=True)


def buscar_columna(df: pd.DataFrame, alias: list[str]) -> str | None:
    cols = {normalizar(c): c for c in df.columns}
    for a in alias:
        if normalizar(a) in cols:
            return cols[normalizar(a)]
    for a in alias:  # coincidencia parcial
        for n, original in cols.items():
            if normalizar(a) in n:
                return original
    return None


def hacer_id(*partes) -> str:
    return hashlib.sha1("|".join(str(p) for p in partes).encode(), usedforsecurity=False).hexdigest()  # solo para deduplicar


def _base_movimiento(fuente: str, carga_id: str, usuario: str) -> dict:
    return {
        "fuente": fuente, "carga_id": carga_id, "creado_por": usuario,
        "creado_en": datetime.now(UTC), "confianza": None, "sugerencia": None,
        "archivo_url": None, "noches": None, "referencia": None,
    }


# ---------------------------------------------------------------- Airbnb

ALIAS_AIRBNB = {
    "fecha": ["Date", "Fecha", "Data"],
    "inicio": ["Start date", "Fecha de inicio", "Data de início", "Data de inicio", "Check-in"],
    "tipo": ["Type", "Tipo"],
    "codigo": ["Confirmation code", "Código de confirmación", "Código de confirmação", "Codigo"],
    "noches": ["Nights", "Noches", "Noites"],
    "huesped": ["Guest", "Huésped", "Hóspede", "Huesped"],
    "anuncio": ["Listing", "Anuncio", "Anúncio"],
    "moneda": ["Currency", "Moneda", "Moeda"],
    "monto": ["Amount", "Monto", "Importe", "Valor"],
    "servicio": ["Service fee", "Tarifa de servicio", "Taxa de serviço", "Comisión de servicio"],
    "bruto": ["Gross earnings", "Ganancias brutas", "Ingresos brutos", "Ganhos brutos"],
}
TIPOS_RESERVA = {"reservation", "reserva"}
TIPOS_PAGO = {"payout", "pago", "pagamento", "pago enviado", "transferencia"}
TIPOS_AJUSTE = ("adjustment", "ajuste", "resolution", "resolucion", "resolucao")


def asignar_propiedad(anuncio: str, propiedades: pd.DataFrame) -> str | None:
    if not anuncio:
        return None
    n = normalizar(anuncio)
    for _, p in propiedades.iterrows():
        if p.get("anuncio_airbnb") and normalizar(p["anuncio_airbnb"]) == n:
            return p["propiedad_id"]
    for _, p in propiedades.iterrows():
        a = p.get("anuncio_airbnb")
        if a and (normalizar(a) in n or n in normalizar(a)):
            return p["propiedad_id"]
    return None


def parse_airbnb(df: pd.DataFrame, propiedades: pd.DataFrame, carga_id: str, usuario: str) -> tuple[pd.DataFrame, dict]:
    """CSV de 'Historial de transacciones' de Airbnb -> ingresos (bruto) + gasto (comisión)."""
    col = {k: buscar_columna(df, v) for k, v in ALIAS_AIRBNB.items()}
    faltan = [k for k in ("tipo", "monto") if not col[k]]
    if faltan:
        raise ValueError(
            "El archivo no parece un CSV de transacciones de Airbnb (faltan columnas: "
            + ", ".join(faltan) + "). Descárgalo desde Ganancias → Historial de transacciones → Exportar CSV."
        )
    fechas_inicio = parse_fechas(df[col["inicio"]]) if col["inicio"] else None
    fechas = parse_fechas(df[col["fecha"]]) if col["fecha"] else None

    filas, resumen = [], {"reservas": 0, "ajustes": 0, "pagos_omitidos": 0, "otros_omitidos": 0}
    for i, r in df.iterrows():
        tipo = normalizar(r[col["tipo"]])
        fecha = (fechas_inicio[i] if fechas_inicio is not None and pd.notna(fechas_inicio[i]) else None) \
            or (fechas[i] if fechas is not None else None)
        if tipo in TIPOS_PAGO or not tipo:
            resumen["pagos_omitidos"] += 1
            continue
        if fecha is None or pd.isna(fecha):
            resumen["otros_omitidos"] += 1
            continue
        anuncio = r[col["anuncio"]] if col["anuncio"] else ""
        propiedad = asignar_propiedad(anuncio, propiedades)
        moneda = (r[col["moneda"]] if col["moneda"] else None) or "CLP"
        codigo = (r[col["codigo"]] if col["codigo"] else None) or f"fila{i}"
        neto = parse_monto(r[col["monto"]]) or 0.0
        servicio = abs(parse_monto(r[col["servicio"]]) or 0.0) if col["servicio"] else 0.0
        bruto = parse_monto(r[col["bruto"]]) if col["bruto"] else None
        bruto = bruto if bruto else neto + servicio
        estado = "OK" if propiedad else "PENDIENTE"
        huesped = r[col["huesped"]] if col["huesped"] else ""
        base = _base_movimiento("AIRBNB_CSV", carga_id, usuario)

        if tipo in TIPOS_RESERVA:
            resumen["reservas"] += 1
            noches = parse_monto(r[col["noches"]]) if col["noches"] else None
            filas.append({**base,
                "movimiento_id": hacer_id("AIRBNB", codigo, "INGRESO"), "fecha": fecha,
                "propiedad_id": propiedad, "tipo": "INGRESO", "categoria": "reserva_airbnb",
                "monto": abs(bruto), "moneda": moneda, "descripcion": f"Reserva {huesped} — {anuncio}".strip(),
                "referencia": codigo, "noches": int(noches) if noches else None,
                "estado": estado, "clasificado_por": "AIRBNB"})
            if servicio:
                filas.append({**base,
                    "movimiento_id": hacer_id("AIRBNB", codigo, "COMISION"), "fecha": fecha,
                    "propiedad_id": propiedad, "tipo": "GASTO", "categoria": "comision_airbnb",
                    "monto": servicio, "moneda": moneda, "descripcion": f"Comisión Airbnb {codigo}",
                    "referencia": codigo, "estado": estado, "clasificado_por": "AIRBNB"})
        elif tipo.startswith(TIPOS_AJUSTE):
            resumen["ajustes"] += 1
            filas.append({**base,
                "movimiento_id": hacer_id("AIRBNB", codigo, tipo, i, neto), "fecha": fecha,
                "propiedad_id": propiedad, "tipo": "INGRESO" if neto >= 0 else "GASTO",
                "categoria": "ajuste_airbnb" if neto >= 0 else "ajuste_airbnb_cargo",
                "monto": abs(neto), "moneda": moneda, "descripcion": f"{r[col['tipo']]} — {anuncio}",
                "referencia": codigo, "estado": estado, "clasificado_por": "AIRBNB"})
        else:
            resumen["otros_omitidos"] += 1
    out = pd.DataFrame(filas, columns=COLUMNAS_MOV)
    return out, resumen


# ---------------------------------------------------------------- Cartolas bancarias

ALIAS_BANCO = {
    "fecha": ["Fecha", "Fecha operación", "Fecha movimiento", "Date", "Data"],
    "descripcion": ["Descripción", "Descripcion", "Detalle", "Glosa", "Movimiento", "Concepto", "Description"],
    "cargo": ["Cargo", "Cargos", "Débito", "Debito", "Egreso", "Giro", "Monto cargo", "Cargos ($)"],
    "abono": ["Abono", "Abonos", "Crédito", "Credito", "Depósito", "Ingreso", "Abonos ($)"],
    "monto": ["Monto", "Importe", "Valor", "Amount"],
}


def detectar_columnas_banco(df: pd.DataFrame) -> dict:
    return {k: buscar_columna(df, v) for k, v in ALIAS_BANCO.items()}


def parse_banco(df: pd.DataFrame, mapeo: dict, moneda: str, carga_id: str, usuario: str,
                incluir_abonos: bool = False) -> pd.DataFrame:
    """Cartola -> gastos (cargos). Los abonos se ignoran por defecto porque los pagos de
    Airbnb ya se registran desde el CSV de Airbnb."""
    if not mapeo.get("fecha") or not mapeo.get("descripcion") or not (mapeo.get("cargo") or mapeo.get("monto")):
        raise ValueError("Elige al menos las columnas de fecha, descripción y cargo (o monto).")
    fechas = parse_fechas(df[mapeo["fecha"]])
    filas, vistos = [], {}
    for i, r in df.iterrows():
        desc = str(r[mapeo["descripcion"]] or "").strip()
        cargo = parse_monto(r[mapeo["cargo"]]) if mapeo.get("cargo") else None
        abono = parse_monto(r[mapeo["abono"]]) if mapeo.get("abono") else None
        if cargo is None and abono is None and mapeo.get("monto"):
            m = parse_monto(r[mapeo["monto"]])
            if m is not None:
                cargo, abono = (abs(m), None) if m < 0 else (None, m)
        if cargo:
            tipo, monto = "GASTO", abs(cargo)
        elif abono and incluir_abonos:
            tipo, monto = "INGRESO", abs(abono)
        else:
            continue
        fecha = fechas[i]
        if fecha is None or pd.isna(fecha):
            continue
        clave = (fecha, desc, monto, tipo)
        vistos[clave] = vistos.get(clave, 0) + 1  # dos cargos idénticos el mismo día = 2 movimientos
        filas.append({**_base_movimiento("BANCO", carga_id, usuario),
            "movimiento_id": hacer_id("BANCO", fecha, desc, monto, tipo, vistos[clave]),
            "fecha": fecha, "propiedad_id": None, "tipo": tipo, "categoria": None,
            "monto": monto, "moneda": moneda, "descripcion": desc,
            "estado": "PENDIENTE", "clasificado_por": None})
    return pd.DataFrame(filas, columns=COLUMNAS_MOV)

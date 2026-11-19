"""Clasificación de movimientos: primero reglas fijas (gratis), después Claude Haiku
solo para lo que las reglas no resuelven. Lo dudoso queda PENDIENTE para revisión humana."""
from __future__ import annotations

import json
import re

import anthropic
import pandas as pd

from .config import IA_ACTIVA, MODELO_CLAUDE, UMBRAL_CONFIANZA


def aplicar_reglas(movs: pd.DataFrame, reglas: pd.DataFrame) -> pd.DataFrame:
    movs = movs.copy()
    reglas = reglas.sort_values("prioridad")
    for idx, m in movs.iterrows():
        if m["estado"] != "PENDIENTE":
            continue
        desc = str(m["descripcion"] or "").upper()
        for _, r in reglas.iterrows():
            if str(r["patron"]).upper() in desc:
                if pd.isna(m["categoria"]) or not m["categoria"]:
                    movs.at[idx, "categoria"] = r["categoria"]
                if pd.notna(r["propiedad_id"]) and r["propiedad_id"]:
                    movs.at[idx, "propiedad_id"] = r["propiedad_id"]
                movs.at[idx, "clasificado_por"] = "REGLA"
                break
        if movs.at[idx, "categoria"] == "__DESCARTAR__":
            movs.at[idx, "estado"] = "DESCARTADO"  # p. ej. transferencias a caja chica (ya están en la planilla)
            continue
        listo = pd.notna(movs.at[idx, "categoria"]) and pd.notna(movs.at[idx, "propiedad_id"])
        if listo:
            movs.at[idx, "estado"] = "OK"
    return movs


_PROMPT = """Eres asistente contable de un negocio de arriendo de corto plazo (Airbnb) en Chile y Brasil.
Clasifica cada movimiento bancario en UNA categoría de la lista y, si se puede deducir, en UNA propiedad.
Si un gasto es del negocio en general (contador, software, publicidad), usa la propiedad GENERAL.
Si no hay forma de saber la propiedad, deja "propiedad_id": null. No inventes códigos.

PROPIEDADES (propiedad_id: nombre, ciudad):
{propiedades}

CATEGORÍAS DE GASTO (categoria: descripción):
{categorias}

MOVIMIENTOS (id: fecha | monto moneda | descripción):
{movimientos}

Responde SOLO con un arreglo JSON, un objeto por movimiento:
[{{"id": "...", "categoria": "...", "propiedad_id": "..." o null, "confianza": 0.0-1.0}}]
La confianza debe ser baja (<0.6) si la descripción es ambigua."""


def clasificar_con_ia(movs: pd.DataFrame, propiedades: pd.DataFrame, categorias: pd.DataFrame,
                      cliente: anthropic.Anthropic | None = None, lote: int = 60) -> pd.DataFrame:
    movs = movs.copy()
    falta = movs[(movs["estado"] == "PENDIENTE") & (movs["tipo"] == "GASTO")]
    if falta.empty or (cliente is None and not IA_ACTIVA):
        return movs  # sin API: quedan en Pendientes (la tarea agendada deja sugerencias)
    cliente = cliente or anthropic.Anthropic()
    txt_prop = "\n".join(f"- {p.propiedad_id}: {p.nombre}, {p.ciudad or ''}" for p in propiedades.itertuples())
    cat_gasto = categorias[categorias["tipo"] == "GASTO"]
    txt_cat = "\n".join(f"- {c.categoria}: {c.descripcion}" for c in cat_gasto.itertuples())
    validas_cat, validas_prop = set(cat_gasto["categoria"]), set(propiedades["propiedad_id"])

    for inicio in range(0, len(falta), lote):
        parte = falta.iloc[inicio:inicio + lote]
        txt_mov = "\n".join(
            f"- {m.movimiento_id[:12]}: {m.fecha} | {m.monto:,.0f} {m.moneda} | {m.descripcion}"
            for m in parte.itertuples()
        )
        resp = cliente.messages.create(
            model=MODELO_CLAUDE, max_tokens=4000,
            messages=[{"role": "user", "content": _PROMPT.format(
                propiedades=txt_prop, categorias=txt_cat, movimientos=txt_mov)}],
        )
        texto = "".join(b.text for b in resp.content if b.type == "text")
        encontrado = re.search(r"\[.*\]", texto, re.S)
        try:
            resultados = json.loads(encontrado.group(0)) if encontrado else []
        except json.JSONDecodeError:
            resultados = []
        por_id = {str(r.get("id")): r for r in resultados}
        for idx, m in parte.iterrows():
            r = por_id.get(m["movimiento_id"][:12])
            if not r:
                continue
            cat = r.get("categoria") if r.get("categoria") in validas_cat else None
            prop = r.get("propiedad_id") if r.get("propiedad_id") in validas_prop else None
            conf = float(r.get("confianza") or 0)
            movs.at[idx, "confianza"] = conf
            movs.at[idx, "sugerencia"] = f"{cat or '?'} / {prop or '?'}"
            if cat and prop and conf >= UMBRAL_CONFIANZA:
                movs.at[idx, "categoria"] = cat
                movs.at[idx, "propiedad_id"] = prop
                movs.at[idx, "estado"] = "OK"
                movs.at[idx, "clasificado_por"] = "IA"
            else:
                # deja la sugerencia precargada para que la persona solo confirme
                if cat:
                    movs.at[idx, "categoria"] = cat
                if prop:
                    movs.at[idx, "propiedad_id"] = prop
    return movs


_PROMPT_BOLETA = """Lee esta boleta o factura y responde SOLO con JSON:
{"fecha": "AAAA-MM-DD", "monto_total": número sin separadores, "moneda": "CLP" o "BRL",
 "proveedor": "...", "numero_documento": "...", "detalle": "resumen de 1 línea de lo comprado"}
Usa null en lo que no se lea con claridad."""


def leer_boleta(imagen: bytes, media_type: str, cliente: anthropic.Anthropic | None = None) -> dict:
    """Extrae datos de la foto de una boleta para precargar el formulario."""
    import base64
    if cliente is None and not IA_ACTIVA:
        return {}
    cliente = cliente or anthropic.Anthropic()
    resp = cliente.messages.create(
        model=MODELO_CLAUDE, max_tokens=500,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                          "data": base64.b64encode(imagen).decode()}},
            {"type": "text", "text": _PROMPT_BOLETA},
        ]}],
    )
    texto = "".join(b.text for b in resp.content if b.type == "text")
    encontrado = re.search(r"\{.*\}", texto, re.S)
    try:
        return json.loads(encontrado.group(0)) if encontrado else {}
    except json.JSONDecodeError:
        return {}

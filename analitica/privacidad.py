"""Protección de datos antes de guardar citas o de subir a BigQuery.

- anonimizar(): quita emails, teléfonos y RUT/CPF de un texto (mismos patrones que
  business/anonimizar.py de andina_lab, que además quita el nombre del huésped al importar).
- seudonimo(): HMAC-SHA256 con SEUDONIMO_CLAVE. El mismo código siempre da el mismo seudónimo
  (los cruces entre tablas en BigQuery siguen funcionando), pero sin la clave no se puede
  volver al código real de la reserva.
"""
import hashlib
import hmac
import re

from .config import SEUDONIMO_CLAVE

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
DOCUMENTO = re.compile(r"(?<!\w)(?<!\d\.)(?:\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]|\d{3}\.?\d{3}\.?\d{3}-\d{2})(?!\w|\.\d)")
TELEFONO = re.compile(r"(?<!\w)(?<!\d\.)\+?\(?\d[\d\s()-]{6,}\d(?!\w|\.\d)")
FECHA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _telefono(m):
    texto = m.group(0)
    if FECHA_ISO.fullmatch(texto.strip()) or sum(c.isdigit() for c in texto) < 8:
        return texto
    return "[teléfono]"


def anonimizar(texto):
    if not isinstance(texto, str) or not texto:
        return texto
    texto = EMAIL.sub("[email]", texto)
    texto = DOCUMENTO.sub("[documento]", texto)
    return TELEFONO.sub(_telefono, texto)


def seudonimo(valor):
    """'HM4X2...' -> 'r_3f9a1c...' (16 hex). None/vacío se mantiene."""
    if valor is None or (isinstance(valor, float) and valor != valor) or str(valor).strip() == "":
        return None
    if not SEUDONIMO_CLAVE:
        raise RuntimeError("Falta SEUDONIMO_CLAVE en el archivo .env (ver .env.example).")
    h = hmac.new(SEUDONIMO_CLAVE.encode(), str(valor).strip().encode("utf-8"), hashlib.sha256).hexdigest()
    return "r_" + h[:16]

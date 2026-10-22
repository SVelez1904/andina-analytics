"""Configuración leída del archivo .env de la carpeta andina_analytics."""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _req(nombre):
    valor = os.environ.get(nombre)
    if not valor:
        raise RuntimeError(f"Falta {nombre} en el archivo .env de andina_analytics (ver .env.example).")
    return valor


DB = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "5432")),
    "dbname": os.environ.get("DB_NAME", "stays"),
    "user": os.environ.get("ANALITICA_DB_USER", "analitica_app"),
    "password": os.environ.get("ANALITICA_DB_PASSWORD", ""),
    "sslmode": os.environ.get("DB_SSLMODE", "disable"),
}

# BigQuery: la app de Streamlit lee de aquí (python -m analitica.subir_bigquery copia los datos)
GCP_PROJECT = os.environ.get("GCP_PROJECT", "")
BQ_LOCATION = os.environ.get("BQ_LOCATION", "US")

ANTHROPIC_API_KEY =os.environ.get("ANTHROPIC_API_KEY", "")
MODELO_REVIEWS = os.environ.get("CLAUDE_MODELO_REVIEWS", "claude-haiku-4-5-20251001")
MODELO_REPORTE = os.environ.get("CLAUDE_MODELO_REPORTE", "claude-haiku-4-5-20251001")

# Primera fecha de reserva confiable (antes, las reservas migradas a Stays aparecen "creadas" el 15-05-2026)
CONFIABLE_DESDE = os.environ.get("CONFIABLE_DESDE", "2026-05-16")

CARPETA_REPORTES = RAIZ / "reportes"

# Meta de ingresos por alojamiento de todo el portafolio, en CLP por mes (Brasil se convierte a CLP).
# Es el KPI de rendimiento financiero del reporte semanal y del dashboard.
META_INGRESO_MENSUAL_CLP = float(os.environ.get("META_INGRESO_MENSUAL_CLP", "14000000"))

# Orden fijo de los mercados en reportes y dashboard: Chile siempre antes que Brasil
ORDEN_MERCADO = {"Chile": 0, "CLP": 0, "Brasil": 1, "BRL": 1}


def clave_mercado(serie):
    """Para sort_values(key=...): Chile (o CLP) antes que Brasil (o BRL); las demás columnas quedan igual."""
    if serie.name in ("mercado", "moneda", "moneda_local"):
        return serie.map(lambda v: ORDEN_MERCADO.get(v, len(ORDEN_MERCADO)))
    return serie


def estado_meta(cumplimiento):
    """cumplimiento = valor / meta -> 'En meta' (>= 100 %), 'Cerca' (>= 70 %) o 'Lejos'."""
    if cumplimiento is None or cumplimiento != cumplimiento:
        return "Sin dato"
    return "En meta" if cumplimiento >= 1 else "Cerca" if cumplimiento >= 0.7 else "Lejos"

# Precios de referencia (USD por millón de tokens) para estimar costos; revisa la página de precios
PRECIOS_USD_MTOK = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-5-5": (2.0, 10.0)}


def precio(modelo):
    for prefijo, p in PRECIOS_USD_MTOK.items():
        if modelo.startswith(prefijo):
            return p
    return (1.0, 5.0)

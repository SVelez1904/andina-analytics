"""Configuración leída de variables de entorno (Cloud Run las define en el despliegue)."""
import os

PROYECTO = os.environ.get("GCP_PROYECTO") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
DATASET = os.environ.get("BQ_DATASET", "finanzas")
MODELO_CLAUDE = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
BUCKET_BOLETAS = os.environ.get("BUCKET_BOLETAS", "")
# Usuario para probar en tu computador (en Cloud Run el usuario lo entrega IAP)
USUARIO_DEV = os.environ.get("DEV_USER", "")
# Límite de seguridad por consulta en BigQuery (1 GB); tus datos pesan mucho menos
MAX_BYTES_CONSULTA = int(os.environ.get("BQ_MAX_BYTES", 1_000_000_000))
# Bajo este nivel de confianza, lo que clasifica la IA queda PENDIENTE para revisión humana
UMBRAL_CONFIANZA = float(os.environ.get("UMBRAL_CONFIANZA", 0.8))
# Sin ANTHROPIC_API_KEY la app funciona igual: clasifica con reglas, lo demás queda en Pendientes,
# la boleta se ingresa a mano y el chat se desactiva. El análisis lo hace una tarea agendada de Claude.
IA_ACTIVA = bool(os.environ.get("ANTHROPIC_API_KEY"))


def tabla(nombre: str) -> str:
    """Nombre completo de una tabla o vista, listo para SQL."""
    return f"`{PROYECTO}.{DATASET}.{nombre}`"


def tabla_id(nombre: str) -> str:
    """Nombre completo sin comillas (para la API de carga)."""
    return f"{PROYECTO}.{DATASET}.{nombre}"

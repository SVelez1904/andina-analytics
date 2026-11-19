"""Exporta en un archivo Markdown todo lo que Claude necesita para el análisis mensual
(lo usa la tarea agendada de Claude, sin API key). No modifica nada en BigQuery.

Uso:  python scripts/datos_para_claude.py [AAAA-MM]      (por defecto, el mes anterior)
Sale: salidas/datos_AAAA-MM.md
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from informe.informe_mensual import PROMPT, _primer_dia_mes_anterior, datos  # noqa: E402
from lib import bq  # noqa: E402
from lib.config import tabla  # noqa: E402


def _csv(df) -> str:
    return df.map(lambda v: float(v) if isinstance(v, Decimal) else v).to_csv(index=False)


def main() -> None:
    mes = date.fromisoformat(sys.argv[1] + "-01") if len(sys.argv) > 1 else _primer_dia_mes_anterior(date.today())
    pend = bq.consultar(f"""SELECT movimiento_id, fecha, tipo, monto, moneda, descripcion, fuente
        FROM {tabla('movimientos')} WHERE estado = 'PENDIENTE' ORDER BY fecha DESC LIMIT 300""")
    props = bq.consultar(f"SELECT propiedad_id, nombre, ciudad, modelo_negocio FROM {tabla('propiedades')} WHERE activa")
    cats = bq.consultar(f"SELECT categoria, tipo, descripcion FROM {tabla('categorias')} ORDER BY tipo, categoria")

    instrucciones = PROMPT.split("DATOS:")[0].strip()
    texto = f"""# Datos para el informe de {mes:%m/%Y}

## Instrucciones del informe
{instrucciones}

## Datos del mes
{datos(mes)}

## Movimientos pendientes de clasificar ({len(pend)})
Para cada uno, sugiere propiedad_id y categoria SOLO de las listas de abajo, con una confianza de 0 a 1.
Si un movimiento es una transferencia a caja chica o a personal de limpieza (ya registrado en las planillas),
sugiere la categoria __DESCARTAR__.

{_csv(pend)}
### Propiedades válidas
{_csv(props)}
### Categorías válidas
{_csv(cats)}
"""
    salida = RAIZ / "salidas" / f"datos_{mes:%Y-%m}.md"
    salida.parent.mkdir(exist_ok=True)
    salida.write_text(texto, encoding="utf-8")
    print(salida)


if __name__ == "__main__":
    main()

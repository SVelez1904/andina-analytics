"""Carga masiva: importa todas las planillas de una carpeta (por ejemplo, '3. OPERATIONS' descargada de Drive).

Uso:  python scripts/importar_operaciones.py "ruta/a/3. OPERATIONS" --usuario tu-email@gmail.com
Los presupuestos toman la propiedad del nombre de su carpeta ("1. Boho 509" → BOHO-509).
Se omiten las planillas personales y las que no se reconocen.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import bq  # noqa: E402
from lib.config import tabla  # noqa: E402
from lib.importar_operaciones import importar, resumen_texto  # noqa: E402
from lib.operaciones import MapaPropiedades  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta")
    ap.add_argument("--usuario", default="carga-masiva")
    args = ap.parse_args()
    mapa = MapaPropiedades(bq.consultar(f"SELECT alias, propiedad_id FROM {tabla('alias_propiedades')}"))
    for f in sorted(Path(args.carpeta).rglob("*.xlsx")):
        if f.name.startswith("~$") or "pessoais" in f.name.lower() or "personal" in f.name.lower():
            print(f"— omitido: {f.name}")
            continue
        carpeta = f.parent.name.split(".", 1)[-1].strip()  # "1. Boho 509" → "Boho 509"
        r = importar(f.read_bytes(), f.name, args.usuario, propiedad_presupuesto=mapa(carpeta))
        print(f"[{r['tipo']}] {f.name}: {resumen_texto(r)}")


if __name__ == "__main__":
    main()

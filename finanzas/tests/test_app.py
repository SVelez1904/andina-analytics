"""Pruebas de humo de la interfaz con Streamlit AppTest: cada página se ejecuta completa
con BigQuery y el usuario simulados. Detecta errores de importación, nombres y columnas."""
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import lib.auth
import lib.bq

RAIZ = Path(__file__).resolve().parents[1]


def _consultar_falso(sql, params=None):
    s = " ".join(sql.split()).lower()
    if "from" in s and "pnl_anual" in s:
        return pd.DataFrame([{"propiedad_id": "ENCINA-911", "propiedad": "Encina 911", "modelo_negocio": "ARBITRAJE",
                              "moneda": "CLP", "anio": 2026, "ingresos": Decimal("1000"), "comisiones": Decimal("30"),
                              "gastos_operativos": Decimal("200"), "mantenimiento": Decimal("50"),
                              "gastos_fijos": Decimal("300"), "resultado": Decimal("420"), "margen": 0.42,
                              "roi_anual": 0.1, "noches_vendidas": 20, "adr": Decimal("50")}])
    if "pnl_mensual" in s and "group by moneda" not in s:
        return pd.DataFrame([{"propiedad_id": "ENCINA-911", "propiedad": "Encina 911", "moneda": "CLP",
                              "mes": pd.Timestamp("2026-10-01"), "anio": 2026, "ingresos": Decimal("1000"),
                              "comisiones": Decimal("30"), "gastos_operativos": Decimal("200"),
                              "mantenimiento": Decimal("50"), "gastos_fijos": Decimal("300"),
                              "gastos_totales": Decimal("580"), "resultado": Decimal("420"), "margen": 0.42,
                              "ocupacion": 0.6, "adr": Decimal("50")}])
    if "group by moneda" in s:
        return pd.DataFrame([{"moneda": "CLP", "ingresos": Decimal("1000"), "gastos": Decimal("580"), "resultado": Decimal("420")}])
    if "count(*) n" in s:
        return pd.DataFrame([{"n": 0}])
    if "estado = 'pendiente'" in s:
        return pd.DataFrame(columns=["movimiento_id", "fecha", "tipo", "monto", "moneda", "descripcion",
                                     "propiedad_id", "categoria", "sugerencia", "confianza", "fuente"])
    if "from" in s and "propiedades" in s:
        return pd.DataFrame([{"propiedad_id": "ENCINA-911", "nombre": "Encina 911", "ciudad": "Providencia"}])
    if "categorias" in s:
        return pd.DataFrame([{"categoria": "limpieza", "tipo": "GASTO", "grupo": "OPERATIVO", "descripcion": "Limpieza"}])
    return pd.DataFrame()


@pytest.fixture(autouse=True)
def simular(monkeypatch):
    monkeypatch.setattr(lib.bq, "consultar", _consultar_falso)
    monkeypatch.setattr(lib.auth, "usuario_actual",
                        lambda: lib.auth.Usuario(email="ana@test.cl", nombre="Ana", rol="ADMIN"))


@pytest.mark.parametrize("pagina", ["app.py", "pages/1_Cargar_datos.py", "pages/2_Registrar_gasto.py",
                                    "pages/3_Pendientes.py", "pages/4_Rentabilidad.py", "pages/5_Asistente.py"])
def test_pagina_carga_sin_errores(pagina):
    at = AppTest.from_file(str(RAIZ / pagina), default_timeout=30).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title, "la página no mostró título"


def test_propietario_no_ve_cargar_datos(monkeypatch):
    monkeypatch.setattr(lib.auth, "usuario_actual",
                        lambda: lib.auth.Usuario(email="d@test.cl", nombre="Dueño", rol="PROPIETARIO", propiedades=["ENCINA-911"]))
    at = AppTest.from_file(str(RAIZ / "pages/1_Cargar_datos.py"), default_timeout=30).run()
    assert any("solo para el equipo administrador" in w.value for w in at.warning)

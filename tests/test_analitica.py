"""Pruebas sin base de datos:  pytest -q"""
import math
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd

from analitica import pronostico, reporte, reviews_ia


# -- Pronóstico -----------------------------------------------------------------------------

def noches_sinteticas():
    """Dos propiedades, mayo-octubre 2026; cada noche se vende 10 días antes, salvo los lunes."""
    filas = []
    for p, nombre in (("A", "Depto A"), ("B", "Depto B")):
        for d in pd.date_range("2026-05-01", "2026-10-31"):
            vendida = d.weekday() != 0
            filas.append({"id_propriedade": p, "nome_anuncio": nombre, "fecha": d, "vendida": vendida,
                          "fecha_reserva": d - pd.Timedelta(days=10) if vendida else pd.NaT,
                          "ingreso_noche_local": 50000.0 if vendida else None, "moneda_local": "CLP"})
    return pronostico.preparar(pd.DataFrame(filas))


def test_curva_monotona_y_en_rango():
    tasa, factores, n = pronostico.curva(noches_sinteticas(), "2026-09-01", "2026-05-16")
    assert n > 0
    assert np.all(np.diff(tasa) >= 0)            # más anticipación, más probabilidad
    assert 0 <= tasa.min() and tasa.max() <= 1
    assert tasa[0] < tasa[30]                    # a 0 días casi no se vende; a 30 sí
    assert set(factores) == {"A", "B"}


def test_pronostico_respeta_lo_reservado():
    df = noches_sinteticas()
    mes, noches, _, _ = pronostico.pronosticar(df, {}, "2026-09-01", meses=1)
    assert len(mes) == 2 and (mes["disponibles"] == 30).all()
    assert (mes["noches_pronostico"] >= mes["reservadas_ya"]).all()
    assert (mes["noches_pronostico"] <= mes["disponibles"]).all()
    assert noches.loc[noches["reservada"], "probabilidad"].eq(1).all()


def test_pronostico_corta_en_fecha_de_baja():
    df = noches_sinteticas()
    mes, _, _, _ = pronostico.pronosticar(df, {"B": pd.Timestamp("2026-09-10")}, "2026-09-01", meses=1)
    assert int(mes.set_index("id_propriedade").loc["B", "disponibles"]) == 10


# -- Reviews con IA ------------------------------------------------------------------------------

def test_mensaje_sin_datos_personales():
    r = {"id_avaliacion": 1, "propiedad": "ENCINA 911", "rating_general": 4, "rating_limpieza": 3,
         "rating_exactitud": None, "comentario_publico": "Todo bien", "comentario_privado": None,
         "nombre_huesped": "Juana Pérez", "codigo_reserva_externo": "HM123"}
    m = reviews_ia.armar_mensaje(r)
    assert "ENCINA 911" in m and "Limpieza: 3" in m and "(vacío)" in m
    assert "Juana" not in m and "HM123" not in m


def test_extraer_descarta_temas_invalidos():
    resp = NS(content=[NS(type="tool_use", name="registrar_temas", input={"temas": [
        {"tema": "limpieza", "sentimiento": "negativo", "severidad": 2, "cita": "sucio", "fuente": "publico"},
        {"tema": "inventado", "sentimiento": "negativo", "cita": "x", "fuente": "publico"},
        {"tema": "wifi_tv", "sentimiento": "enojado", "cita": "x", "fuente": "publico"},
    ]})])
    temas = reviews_ia.extraer(resp)
    assert [t["tema"] for t in temas] == ["limpieza"]


def test_filas_a_guardar():
    filas = reviews_ia.filas_a_guardar(7, [
        {"tema": "ubicacion", "sentimiento": "positivo", "severidad": 3, "cita": "cerca de todo",
         "fuente": "publico", "accion_sugerida": "nada"},
        {"tema": "bano", "sentimiento": "neutro", "cita": "faltó jabón", "fuente": "privado"},
    ], "modelo")
    assert filas[0]["sev"] is None and filas[0]["acc"] is None      # positivos sin severidad ni acción
    assert filas[1]["sev"] == 1                                      # neutro sin severidad -> 1
    vacio = reviews_ia.filas_a_guardar(8, [], "modelo")
    assert vacio[0]["cita"] == reviews_ia.CITA_ELOGIO_GENERAL


# -- Reporte ---------------------------------------------------------------------------------------

def test_formatos():
    assert reporte.dinero(1234567.4, "CLP") == "1.234.567 CLP"
    assert reporte.pct(0.756) == "76%"
    assert reporte.pct(None) == "—"
    assert reporte.pct_airbnb(1.384, 2) == "1.38 %"
    assert reporte.txt(float("nan")) == "—"


def test_sin_nan_produce_json_valido():
    limpio = reporte._sin_nan({"a": float("nan"), "b": [1.0, math.nan], "c": "x"})
    assert limpio == {"a": None, "b": [1.0, None], "c": "x"}


def test_texto_por_reglas():
    n = {"kpis_por_mercado": [{"mercado": "Chile", "moneda": "CLP", "mes": "septiembre 2026", "ocupacion": 0.6,
                               "adr": 50000, "revpar": 30000, "revpar_mes_anterior": 25000}],
         "reviews_criticas_o_alerta": [{"propiedad": "PUCON 403", "criticidad": "Crítico",
                                        "motivo": "acumulado 4.77 < 4.80", "peor_categoria_3m": None}],
         "noches_libres_proximos_7_dias": {"ENCINA 911": 4}}
    t = reporte.texto_por_reglas(n)
    assert "Chile" in t and "+20%" in t and "PUCON 403" in t and "ENCINA 911" in t
    assert "None" not in t and "nan" not in t


def test_chile_primero():
    df = pd.DataFrame({"mercado": ["Brasil", "Chile", "Brasil", "Chile"], "mes": [1, 1, 2, 2]})
    assert reporte.chile_primero(df, ["mercado", "mes"])["mercado"].tolist() == ["Chile", "Chile", "Brasil", "Brasil"]
    pr = pd.DataFrame({"mes": [1, 1], "moneda": ["BRL", "CLP"]})
    assert reporte.chile_primero(pr, ["mes", "moneda"])["moneda"].tolist() == ["CLP", "BRL"]


def test_ingresos_vs_meta():
    from datetime import date

    d = {"corte": date(2026, 10, 22),
         "ingresos": pd.DataFrame({"mes": ["2026-09-01", "2026-10-01"], "ingreso_clp": [15_000_000, 7_000_000]})}
    im = reporte.ingresos_vs_meta(d)
    assert im["meta"].tolist() == [14_000_000, 14_000_000]
    assert im["estado"].tolist() == ["En meta", "Lejos"] and im["en_curso"].tolist() == [False, True]
    assert round(im["cumplimiento"].iloc[1], 2) == 0.5


def test_tabla_md():
    df = pd.DataFrame({"a": ["x|y"], "b": [1]})
    t = reporte.tabla_md(df, [("A", lambda r: r["a"]), ("B", lambda r: r["b"])])
    assert t.splitlines()[0] == "| A | B |" and "x/y" in t
    assert reporte.tabla_md(pd.DataFrame(), []) == "_Sin datos._\n"


# -- Subida a BigQuery ----------------------------------------------------------------------

def test_preparar_tipos_para_bigquery():
    import datetime as dt
    import decimal

    from analitica import subir_bigquery

    df = pd.DataFrame({
        "probabilidad": [decimal.Decimal("0.4500"), None],
        "citas": [["muy limpio", "buena vista"], None],
        "datos": [{"a": 1}, None],
        "vacia": [None, None],
        "fecha": [dt.date(2026, 10, 1), dt.date(2026, 10, 2)],
    })
    out = subir_bigquery.preparar(df)
    assert out["probabilidad"].dtype == "float64" and math.isclose(out["probabilidad"].iloc[0], 0.45)
    assert out["citas"].tolist() == [["muy limpio", "buena vista"], []]   # NULL -> lista vacía
    assert out["datos"].iloc[0] == '{"a": 1}' and pd.isna(out["datos"].iloc[1])
    assert str(out["vacia"].dtype) == "string"
    assert "_cargado_en" in out.columns


def test_objetos_sin_datos_personales():
    from analitica import subir_bigquery

    todos = {t for tablas in subir_bigquery.OBJETOS.values() for t in tablas}
    assert not todos & {"dim_hospedes", "vw_reservas_analisis", "auth_user", "django_session"}

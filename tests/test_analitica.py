"""Pruebas sin base de datos:  pytest -q"""
import math
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

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


# -- Dashboard: piezas de app/comun.py -------------------------------------------------------------

@pytest.fixture
def comun(monkeypatch):
    monkeypatch.syspath_prepend("app")
    import comun
    return comun


def _noches(mes, mercado="Chile", moneda="CLP", **kw):
    fila = dict(mes=pd.Timestamp(mes), mercado=mercado, moneda_local=moneda, noches_vendidas=0, noches_disponibles=30,
                noches_futuras_vendidas=0, noches_pasadas=30, ingreso_alojamiento=0.0, ingreso_futuro=0.0)
    return fila | kw


def test_resumen_mes_separa_a_la_fecha_del_mes_completo(comun):
    kp = pd.DataFrame([
        _noches("2026-11-01", "Brasil", "BRL", noches_pasadas=4),
        _noches("2026-11-01", noches_vendidas=10, noches_futuras_vendidas=7, noches_pasadas=4,
                ingreso_alojamiento=1000.0, ingreso_futuro=700.0),
        _noches("2026-11-01", noches_vendidas=5, noches_futuras_vendidas=3, noches_pasadas=4,
                ingreso_alojamiento=500.0, ingreso_futuro=300.0),
        _noches("2026-10-01", noches_vendidas=99),
    ])
    chile, brasil = (r for _, r in comun.resumen_mes(kp, pd.Timestamp("2026-11-01")).iterrows())
    assert chile["mercado"] == "Chile" and brasil["mercado"] == "Brasil"
    assert chile["vendidas_fecha"] == 5
    assert chile["ocupacion_fecha"] == pytest.approx(5 / 8)
    assert chile["adr_fecha"] == pytest.approx(100)
    assert chile["revpar_fecha"] == pytest.approx(500 / 8)
    assert chile["ocupacion_mes"] == pytest.approx(15 / 60)
    assert brasil["ocupacion_fecha"] == 0 and pd.isna(brasil["adr_fecha"])    # sin ventas: sin ADR, no error


def test_resumen_mes_primer_dia_y_mes_cerrado(comun):
    primer_dia = pd.DataFrame([_noches("2026-11-01", noches_vendidas=9, noches_futuras_vendidas=9, noches_pasadas=0,
                                       ingreso_alojamiento=900.0, ingreso_futuro=900.0)])
    r = comun.resumen_mes(primer_dia, pd.Timestamp("2026-11-01")).iloc[0]
    assert pd.isna(r["ocupacion_fecha"]) and r["ocupacion_mes"] == pytest.approx(9 / 30)

    cerrado = pd.DataFrame([_noches("2026-10-01", noches_vendidas=15, ingreso_alojamiento=1500.0)])
    r = comun.resumen_mes(cerrado, pd.Timestamp("2026-10-01")).iloc[0]
    assert r["ocupacion_fecha"] == r["ocupacion_mes"] == pytest.approx(0.5)


def _reservas(comun, hoy):
    """Una reserva por situación posible, con la misma lógica de terminada/pendiente de reservas_reviews()."""
    hoy = pd.Timestamp(hoy)
    d = lambda n: hoy + pd.Timedelta(days=n)  # noqa: E731
    df = pd.DataFrame([
        ("A", "con", d(-20), d(-15), True, 5.0),
        ("A", "abierta", d(-10), d(-3), False, None),
        ("A", "justo", d(-20), d(-14), False, None),
        ("B", "vencida", d(-20), d(-15), False, None),
        ("B", "encurso", d(-1), d(2), False, None),
        ("C", "futura", d(3), d(6), False, None),
        ("D", "sale_hoy", d(-3), d(0), False, None),
    ], columns=["propiedad", "id_reserva", "llegada", "salida", "con_review", "nota"])
    df["terminada"] = df["salida"] <= hoy
    df["pendiente"] = df["terminada"] & ~df["con_review"] & ((hoy - df["salida"]).dt.days <= comun.DIAS_PARA_REVIEW)
    df["situacion"] = comun.situacion_reserva(df, hoy)
    return df


def test_situacion_de_cada_reserva(comun):
    s = _reservas(comun, "2026-11-20").set_index("id_reserva")["situacion"]
    assert s["con"] == comun.CON_REVIEW
    assert s["abierta"] == s["justo"] == s["sale_hoy"] == comun.PUEDE_DEJARLA     # el día 14 todavía se puede
    assert s["vencida"] == comun.PLAZO_VENCIDO
    assert s["encurso"] == comun.EN_CURSO
    assert s["futura"] == comun.POR_LLEGAR


def test_reviews_por_departamento(comun):
    con, sin = comun.reviews_por_departamento(_reservas(comun, "2026-11-20"))
    assert con["propiedad"].tolist() == ["A"]
    a = con.iloc[0]
    assert (a["con_review"], a["terminadas"], a["pendientes"], a["vencidas"]) == (1, 3, 2, 0)
    assert sin["propiedad"].tolist() == ["D", "B", "C"]      # primero donde todavía se puede conseguir
    b = sin.set_index("propiedad").loc["B"]
    assert (b["vencidas"], b["por_terminar"], b["pendientes"]) == (1, 1, 0)
    assert sin.set_index("propiedad").loc["C", "por_terminar"] == 1


def _reviews_mes(*notas):
    """Una fila por review, como si cada una fuera de un anuncio distinto."""
    return pd.DataFrame({"reviews_con_nota": 1, "suma_general": notas, "nota_minima": notas,
                         "reviews_bajo_5": [int(n < 5) for n in notas]})


@pytest.mark.parametrize("notas, veredicto", [
    ((5,) * 9 + (4,), "🟢"),         # 4,90 justo
    ((5, 5, 5, 5, 4), "🟠"),         # 4,80 justo
    ((5, 5, 4, 4, 5, 4), "🔴"),      # bajo 4,80
    ((5,) * 30 + (3,), "🔴"),        # promedio alto, pero una review de 3 siempre es mal mes
    ((5, 4), "⚪"),                  # muy pocas para evaluar
    ((3,), "🔴"),                    # aunque sea una sola, una review de 3 se avisa
])
def test_evaluar_reviews_veredicto(comun, notas, veredicto):
    assert comun.evaluar_reviews(_reviews_mes(*notas))["veredicto"].startswith(veredicto)


def test_evaluar_reviews_totales_y_mes_vacio(comun):
    r = comun.evaluar_reviews(_reviews_mes(5, 5, 4))
    assert (r["reviews"], r["cinco"], r["minima"]) == (3, 2, 4) and r["nota"] == pytest.approx(14 / 3)
    vacio = comun.evaluar_reviews(_reviews_mes(5).iloc[0:0])
    assert vacio["reviews"] == 0 and vacio["nota"] is None and vacio["veredicto"].startswith("⚪")

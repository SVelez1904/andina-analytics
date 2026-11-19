import pandas as pd

from lib import parsers
from lib.clasificador import aplicar_reglas


def test_montos():
    assert parsers.parse_monto("1.234.567") == 1234567
    assert parsers.parse_monto("$ -12.000") == -12000
    assert parsers.parse_monto("1,234.56") == 1234.56
    assert parsers.parse_monto("1.234,56") == 1234.56
    assert parsers.parse_monto("(5.000)") == -5000
    assert parsers.parse_monto("12.50") == 12.5
    assert parsers.parse_monto("") is None

PROPS = pd.DataFrame([{"propiedad_id": "PUCON", "nombre": "Pucón", "ciudad": "Pucón", "anuncio_airbnb": "Depto vista volcán Pucón"},
                      {"propiedad_id": "GENERAL", "nombre": "General", "ciudad": None, "anuncio_airbnb": None}])

def test_airbnb_en():
    csv = ('Date,Type,Confirmation code,Start date,Nights,Guest,Listing,Details,Currency,Amount,Paid out,Service fee,Cleaning fee,Gross earnings\n'
           '03/04/2026,Reservation,HM123,03/10/2026,3,Ana,Depto vista volcán Pucón,,CLP,"291,000",,"9,000","30,000","300,000"\n'
           '03/12/2026,Payout,,,,,,Transfer,CLP,,"291,000",,,\n'
           '03/15/2026,Resolution Adjustment,HM123,03/10/2026,,,Depto vista volcán Pucón,,CLP,"-20,000",,,,\n'
           '03/20/2026,Reservation,HM999,03/25/2026,2,Bo,Casa desconocida,,CLP,"100,000",,"3,000",,\n')
    df = parsers.leer_tabla(csv.encode(), "a.csv")
    movs, info = parsers.parse_airbnb(df, PROPS, "c1", "yo")
    assert info["reservas"] == 2 and info["pagos_omitidos"] == 1 and info["ajustes"] == 1
    r = movs[movs.categoria == "reserva_airbnb"].iloc[0]
    assert r.monto == 300000 and str(r.fecha) == "2026-03-10" and r.propiedad_id == "PUCON" and r.noches == 3
    assert movs[movs.categoria == "comision_airbnb"].iloc[0].monto == 9000
    assert movs[movs.categoria == "ajuste_airbnb_cargo"].iloc[0].monto == 20000
    desconocida = movs[movs.referencia == "HM999"]
    assert (desconocida.estado == "PENDIENTE").all() and desconocida.iloc[0].monto == 103000
    # mismo archivo => mismos ids (deduplicación)
    movs2, _ = parsers.parse_airbnb(df, PROPS, "c2", "yo")
    assert list(movs.movimiento_id) == list(movs2.movimiento_id)

def test_airbnb_es():
    csv = ('Fecha;Tipo;Código de confirmación;Fecha de inicio;Noches;Huésped;Anuncio;Moneda;Monto;Tarifa de servicio\n'
           '15/04/2026;Reserva;HMX;20/04/2026;2;Eva;Depto vista volcán Pucón;CLP;194.000;6.000\n')
    df = parsers.leer_tabla(csv.encode("latin-1"), "b.csv")
    movs, info = parsers.parse_airbnb(df, PROPS, "c", "yo")
    r = movs[movs.categoria == "reserva_airbnb"].iloc[0]
    assert r.monto == 200000 and str(r.fecha) == "2026-04-20"

def test_banco_con_encabezado_y_reglas():
    csv = ('Banco Ejemplo;;;\nCuenta 123;;;\n'
           'Fecha;Descripción;Cargos ($);Abonos ($)\n'
           '02/05/2026;PAGO ENEL DISTRIBUCION;45.320;\n'
           '03/05/2026;TRANSF AIRBNB PAYMENTS;;291.000\n'
           '04/05/2026;COMPRA SODIMAC;12.990;\n'
           '04/05/2026;COMPRA SODIMAC;12.990;\n'
           '06/05/2026;PRICELABS;19.000;\n')
    df = parsers.leer_tabla(csv.encode(), "c.csv", palabra_encabezado="fecha")
    mapeo = parsers.detectar_columnas_banco(df)
    assert mapeo["cargo"] == "Cargos ($)" and mapeo["descripcion"] == "Descripción"
    movs = parsers.parse_banco(df, mapeo, "CLP", "c", "yo")
    assert len(movs) == 4 and movs.movimiento_id.nunique() == 4  # abono ignorado, 2 Sodimac distintos
    reglas = pd.DataFrame([{"patron": "PRICELABS", "categoria": "software", "propiedad_id": "GENERAL", "prioridad": 10},
                           {"patron": "ENEL", "categoria": "servicios_basicos", "propiedad_id": None, "prioridad": 20}])
    out = aplicar_reglas(movs, reglas)
    pl = out[out.descripcion == "PRICELABS"].iloc[0]
    assert pl.estado == "OK" and pl.propiedad_id == "GENERAL"
    enel = out[out.descripcion.str.contains("ENEL")].iloc[0]
    assert enel.categoria == "servicios_basicos" and enel.estado == "PENDIENTE"  # falta propiedad


def test_sin_api_key_no_llama_a_claude(monkeypatch):
    """Sin ANTHROPIC_API_KEY, los gastos sin regla quedan PENDIENTES y no se crea cliente de Claude."""
    import lib.clasificador as cl
    monkeypatch.setattr(cl, "IA_ACTIVA", False)
    monkeypatch.setattr(cl.anthropic, "Anthropic", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía llamar")))
    movs = pd.DataFrame([{"movimiento_id": "x" * 40, "fecha": "2026-10-01", "monto": 1000.0, "moneda": "CLP",
                          "descripcion": "COMPRA X", "tipo": "GASTO", "estado": "PENDIENTE",
                          "categoria": None, "propiedad_id": None}])
    out = cl.clasificar_con_ia(movs, PROPS, pd.DataFrame({"categoria": ["limpieza"], "tipo": ["GASTO"], "descripcion": ["x"]}))
    assert out.iloc[0].estado == "PENDIENTE"
    assert cl.leer_boleta(b"", "image/png") == {}

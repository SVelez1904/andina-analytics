from datetime import date

import pandas as pd
import streamlit as st

from lib import bq, parsers
from lib.auth import exigir_edicion, usuario_actual
from lib.clasificador import leer_boleta
from lib.config import BUCKET_BOLETAS, IA_ACTIVA
from lib.registro import guardar_movimientos, nueva_carga_id

st.set_page_config(page_title="Registrar gasto", page_icon="🧾")
u = usuario_actual()
exigir_edicion(u)
st.title("Registrar gasto")
st.caption("Para gastos en efectivo o pagados fuera de la cuenta del banco. Sirve desde el celular.")

props = bq.propiedades()
cats = bq.categorias()
cats_gasto = cats[cats["tipo"] == "GASTO"]

foto = st.file_uploader("Foto de la boleta (opcional)", type=["jpg", "jpeg", "png", "webp"])
leido = {}
if foto:
    st.image(foto, width=260)
    if IA_ACTIVA and st.button("Leer boleta con IA"):
        with st.spinner("Leyendo..."):
            st.session_state["boleta"] = leer_boleta(foto.getvalue(), foto.type)
    leido = st.session_state.get("boleta", {})

with st.form("gasto"):
    prop = st.selectbox("Propiedad", props["propiedad_id"], format_func=lambda x: props.set_index("propiedad_id").loc[x, "nombre"])
    cat = st.selectbox("Categoría", cats_gasto["categoria"],
                       format_func=lambda x: cats_gasto.set_index("categoria").loc[x, "descripcion"])
    try:
        f_def = date.fromisoformat(leido.get("fecha") or "")
    except ValueError:
        f_def = date.today()
    fecha = st.date_input("Fecha", f_def)
    monto = st.number_input("Monto", min_value=0.0, step=1000.0, value=float(leido.get("monto_total") or 0))
    moneda = st.radio("Moneda", ["CLP", "BRL"], horizontal=True,
                      index=1 if leido.get("moneda") == "BRL" else 0)
    detalle = st.text_input("Detalle", value=" — ".join(x for x in [leido.get("proveedor"), leido.get("detalle")] if x))
    numero = st.text_input("N° de boleta o factura", value=leido.get("numero_documento") or "")
    enviado = st.form_submit_button("Guardar gasto", type="primary")

if enviado:
    if monto <= 0:
        st.error("Ingresa un monto mayor a cero.")
        st.stop()
    url = None
    if foto and BUCKET_BOLETAS:
        from google.cloud import storage
        nombre = f"{fecha:%Y/%m}/{prop}-{nueva_carga_id()}-{foto.name}"
        storage.Client().bucket(BUCKET_BOLETAS).blob(nombre).upload_from_string(foto.getvalue(), content_type=foto.type)
        url = f"gs://{BUCKET_BOLETAS}/{nombre}"
    carga = nueva_carga_id()
    fila = {c: None for c in parsers.COLUMNAS_MOV} | {
        "movimiento_id": parsers.hacer_id("BOLETA", prop, fecha, monto, numero or carga),
        "fecha": fecha, "propiedad_id": prop, "tipo": "GASTO", "categoria": cat, "monto": monto,
        "moneda": moneda, "descripcion": detalle, "referencia": numero or None, "fuente": "BOLETA",
        "estado": "OK", "clasificado_por": "HUMANO", "archivo_url": url, "carga_id": carga,
        "creado_por": u.email, "creado_en": pd.Timestamp.now(tz="UTC")}
    res = guardar_movimientos(pd.DataFrame([fila]), "BOLETA", foto.name if foto else "manual", u.email, carga, 1)
    st.session_state.pop("boleta", None)
    if res["filas_nuevas"]:
        st.success("Gasto guardado.")
    else:
        st.info("Ese gasto ya estaba registrado.")

import streamlit as st

from lib import bq
from lib.auth import exigir_edicion, usuario_actual
from lib.registro import confirmar, crear_regla, pendientes

st.set_page_config(page_title="Pendientes", page_icon="✅", layout="wide")
u = usuario_actual()
exigir_edicion(u)
st.title("Pendientes por clasificar")

df = pendientes()
if df.empty:
    st.success("No hay nada pendiente.")
    st.stop()

props = bq.propiedades()["propiedad_id"].tolist()
cats = bq.categorias()["categoria"].tolist()

st.caption("Elige propiedad y categoría en cada fila (la sugerencia de la IA ya viene marcada cuando existe). "
           "Marca **Descartar** para movimientos que no son del negocio. Luego presiona **Guardar**.")
df["descartar"] = False
df["crear_regla"] = False
editado = st.data_editor(
    df,
    column_order=["fecha", "descripcion", "monto", "moneda", "propiedad_id", "categoria",
                  "descartar", "crear_regla", "sugerencia"],
    column_config={
        "fecha": st.column_config.DateColumn("Fecha", disabled=True),
        "descripcion": st.column_config.TextColumn("Descripción", disabled=True, width="large"),
        "monto": st.column_config.NumberColumn("Monto", disabled=True, format="%.0f"),
        "moneda": st.column_config.TextColumn("Moneda", disabled=True),
        "propiedad_id": st.column_config.SelectboxColumn("Propiedad", options=props),
        "categoria": st.column_config.SelectboxColumn("Categoría", options=cats),
        "descartar": st.column_config.CheckboxColumn("Descartar"),
        "crear_regla": st.column_config.CheckboxColumn("Recordar para la próxima",
            help="Crea una regla: la próxima vez que aparezca esta descripción se clasifica sola."),
        "sugerencia": st.column_config.TextColumn("Sugerencia IA", disabled=True),
    },
    hide_index=True, use_container_width=True, key="editor",
)

listos = editado[(editado["descartar"]) | (editado["propiedad_id"].notna() & editado["categoria"].notna()
                                           & (editado["propiedad_id"] != "") & (editado["categoria"] != ""))]
st.write(f"{len(listos)} de {len(editado)} filas listas para guardar.")

if st.button("Guardar", type="primary", disabled=listos.empty):
    with st.spinner("Guardando..."):
        n = confirmar(listos, u.email)
        for r in listos[listos["crear_regla"]].itertuples():
            patron = " ".join(str(r.descripcion).split()[:3])  # primeras palabras = comercio
            if r.descartar:
                crear_regla(patron, "__DESCARTAR__", None, prioridad=5)
            else:
                crear_regla(patron, r.categoria, r.propiedad_id)
    st.success(f"{n} movimientos guardados.")
    st.rerun()

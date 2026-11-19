import streamlit as st

from lib.agente import responder
from lib.auth import usuario_actual
from lib.config import IA_ACTIVA

st.set_page_config(page_title="Asistente", page_icon="💬")
u = usuario_actual()
st.title("Asistente financiero")
if not IA_ACTIVA:
    st.info("El chat está desactivado (la app funciona sin API key). Las preguntas sobre los números se responden "
            "en el informe mensual que genera Claude, o en la página Rentabilidad.")
    st.stop()
st.caption("Pregunta en español. Ejemplos: *¿Cuánto ganó Pucón en octubre?* · "
           "*¿Qué propiedad tuvo el peor margen este año?* · *¿En qué gastamos más en mantenimiento?*")

if "api_historial" not in st.session_state:
    st.session_state.api_historial = []   # mensajes completos para Claude (incluye funciones)
    st.session_state.chat = []            # solo lo que se muestra en pantalla

if st.button("Nueva conversación"):
    st.session_state.api_historial, st.session_state.chat = [], []

for rol, texto in st.session_state.chat:
    st.chat_message(rol).markdown(texto)

if pregunta := st.chat_input("Escribe tu pregunta"):
    st.chat_message("user").markdown(pregunta)
    historial = st.session_state.api_historial[-20:]  # memoria corta = menos tokens
    while historial and not (historial[0]["role"] == "user" and isinstance(historial[0]["content"], str)):
        historial = historial[1:]  # empezar siempre con una pregunta de la persona
    historial.append({"role": "user", "content": pregunta})
    with st.chat_message("assistant"):
        with st.spinner("Consultando los datos..."):
            try:
                texto, historial = responder(historial, u.permitidas())
                st.session_state.api_historial = historial
            except Exception as e:
                texto = f"No pude responder ahora ({e.__class__.__name__}). Intenta de nuevo en un momento."
        st.markdown(texto)
    st.session_state.chat += [("user", pregunta), ("assistant", texto)]

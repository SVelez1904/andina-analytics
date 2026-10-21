"""Inicio de sesión con Google (st.login) para el dashboard.

Solo entran cuentas verificadas del dominio DOMINIO que estén en `[access] allowed_emails` (Secrets).
Si falta la configuración, la app queda cerrada. Ver README, sección 8.3.
"""
import streamlit as st

DOMINIO = "andinagroup.cl"


def _correos_permitidos():
    try:
        st.secrets["auth"]
        return {e.strip().lower() for e in st.secrets["access"]["allowed_emails"] if e.strip()}
    except Exception:  # sin secrets.toml, sin [auth] o sin [access]
        return set()


def require_login():
    permitidos = _correos_permitidos()
    if not permitidos:
        st.error("Falta configurar el inicio de sesión: `[auth]` y `[access] allowed_emails` en Secrets "
                 "(ver README, sección 8.3).")
        st.stop()
    if not st.user.get("is_logged_in"):
        st.title("Andina Analytics")
        st.markdown("Ingresa con tu cuenta de Andina Group.")
        st.button("Iniciar sesión con Google", on_click=st.login, type="primary")
        st.stop()
    correo = (st.user.get("email") or "").lower()
    if st.user.get("email_verified") is not True or st.user.get("hd") != DOMINIO or correo not in permitidos:
        st.error(f"La cuenta `{correo}` no tiene acceso. Pide que la agreguen o ingresa con otra cuenta.")
        st.button("Cerrar sesión", on_click=st.logout)
        st.stop()
    with st.sidebar:
        st.caption(correo)
        st.button("Cerrar sesión", on_click=st.logout)

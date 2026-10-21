"""Inicio de sesión con Google (st.login) para el dashboard.

Solo entran cuentas verificadas del dominio DOMINIO que estén en `[access] allowed_emails` (Secrets).
Si falta la configuración, la app queda cerrada. Ver README, sección 8.3.
"""
import streamlit as st

DOMINIO = "andinagroup.cl"


def _correos_permitidos():
    """Devuelve (correos, problema). Si falta algo, correos queda vacío y problema dice qué."""
    try:
        claves = list(st.secrets.keys())
    except Exception:
        return set(), "no se encontraron Secrets (en tu computador: falta `.streamlit/secrets.toml`)"
    vistas = ", ".join(f"`{k}`" for k in claves) or "ninguna"
    if "auth" not in claves:
        return set(), f"falta la sección `[auth]` (secciones que veo: {vistas})"
    if "access" not in claves:
        return set(), f"falta la sección `[access]` (secciones que veo: {vistas})"
    try:
        correos = {e.strip().lower() for e in st.secrets["access"]["allowed_emails"] if e.strip()}
    except Exception as e:
        return set(), f"`[access] allowed_emails` no se pudo leer ({e.__class__.__name__})"
    return correos, "`[access] allowed_emails` está vacío"


def require_login():
    permitidos, problema = _correos_permitidos()
    if not permitidos:
        st.error(f"Falta configurar el inicio de sesión: {problema}. Ver README, sección 8.3.")
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

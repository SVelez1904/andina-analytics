"""Usuario actual. En Cloud Run, IAP ya verificó el login de Google y envía el email en un header.
Aquí solo se decide qué puede ver: ADMIN y OPERADOR ven todo; PROPIETARIO solo sus propiedades."""
from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from . import bq
from .config import USUARIO_DEV, tabla


@dataclass
class Usuario:
    email: str
    nombre: str
    rol: str
    propiedades: list[str] = field(default_factory=list)

    @property
    def ve_todo(self) -> bool:
        return self.rol in ("ADMIN", "OPERADOR")

    @property
    def puede_editar(self) -> bool:
        return self.rol in ("ADMIN", "OPERADOR")

    def permitidas(self) -> list[str] | None:
        """None = todas."""
        return None if self.ve_todo else list(self.propiedades)


def _email_iap() -> str:
    valor = st.context.headers.get("X-Goog-Authenticated-User-Email", "") or USUARIO_DEV
    return valor.split(":")[-1].strip().lower()  # 'accounts.google.com:ana@x.com' -> 'ana@x.com'


@st.cache_data(ttl=600, show_spinner=False)
def _buscar(email: str) -> dict | None:
    df = bq.consultar(
        f"SELECT * FROM {tabla('usuarios')} WHERE LOWER(email) = @e LIMIT 1",
        [bq.p("e", "STRING", email)],
    )
    if df.empty:
        return None
    r = df.iloc[0]
    props = r["propiedades"]
    return {"email": email, "nombre": r["nombre"] or email, "rol": r["rol"],
            "propiedades": list(props) if props is not None else []}


def usuario_actual() -> Usuario:
    email = _email_iap()
    datos = _buscar(email) if email else None
    if not datos:
        st.error(f"Tu cuenta ({email or 'desconocida'}) no tiene acceso. Pide a la administradora que te agregue.")
        st.stop()
    return Usuario(**datos)


def exigir_edicion(u: Usuario) -> None:
    if not u.puede_editar:
        st.warning("Esta página es solo para el equipo administrador.")
        st.stop()

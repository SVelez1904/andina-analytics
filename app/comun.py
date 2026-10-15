"""Piezas compartidas del dashboard: conexión, caché, colores y formatos."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from analitica import db  # noqa: E402

# Colores (paleta validada para daltonismo). Una serie = azul; dos = azul y naranjo.
AZUL, NARANJO, AGUA = "#2a78d6", "#eb6834", "#1baf7a"
AZUL_CLARO = "#86b6ef"
SECUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
GRIS = "#c3c2b7"
ESTADO = {"Crítico": "🔴 Crítico", "Alerta": "🟠 Alerta", "OK": "🟢 OK", "Sin datos suficientes": "⚪ Sin datos suficientes"}
COLOR_MERCADO = {"Chile": AZUL, "Brasil": NARANJO}

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
NOMBRE_TEMA = {
    "limpieza": "Limpieza", "ropa_de_cama": "Ropa de cama", "mantenimiento": "Mantenimiento",
    "equipamiento": "Equipamiento", "cocina": "Cocina", "bano": "Baño", "climatizacion": "Climatización",
    "wifi_tv": "Wifi / TV", "privacidad": "Privacidad", "ruido": "Ruido", "seguridad": "Seguridad",
    "check_in": "Check-in", "comunicacion": "Comunicación", "ubicacion": "Ubicación",
    "precio_valor": "Precio / valor", "exactitud": "Exactitud", "espacio": "Espacio", "vista": "Vista",
    "externo": "Externo", "otro": "Otro",
}


def configurar(titulo):
    st.set_page_config(page_title=f"{titulo} · Andina Analytics", page_icon="📊", layout="wide")
    st.title(titulo)


@st.cache_data(ttl=300, show_spinner=False)
def leer(sql, params=None):
    return db.leer(sql, params)


@st.cache_data(ttl=300, show_spinner=False)
def existe(objeto):
    return db.existe(objeto)


def conexion_ok():
    """Muestra un error claro si no hay conexión; devuelve True/False."""
    try:
        leer("SELECT 1 AS ok")
        return True
    except Exception as e:
        st.error("No me pude conectar a la base. Revisa el archivo `.env` (DB_HOST, ANALITICA_DB_USER, "
                 f"ANALITICA_DB_PASSWORD) y que Docker esté corriendo.\n\nDetalle: `{e.__class__.__name__}`")
        return False


def requiere(objeto, como_crearlo):
    if not existe(objeto):
        st.info(f"Todavía no existe `{objeto}`. {como_crearlo}")
        return False
    return True


def nombre_mes(d, largo=False):
    d = pd.Timestamp(d)
    return f"{MESES[d.month - 1]} {d.year}" if not largo else f"{MESES[d.month - 1]}-{str(d.year)[2:]}"


def dinero(x, moneda=""):
    if x is None or pd.isna(x):
        return "—"
    return f"{float(x):,.0f}".replace(",", ".") + (f" {moneda}" if moneda else "")


def pct(x, dec=0):
    return "—" if x is None or pd.isna(x) else f"{float(x) * 100:.{dec}f} %"


def estilo_figura(fig, alto=360, y_pct=False, leyenda=True):
    fig.update_layout(
        height=alto, margin=dict(l=8, r=8, t=36, b=8), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text="") if leyenda
        else dict(visible=False),
        font=dict(size=13),
    )
    fig.update_xaxes(showgrid=False, title_text="")
    fig.update_yaxes(gridcolor="rgba(137,135,129,0.25)", zeroline=False, title_text="")
    if y_pct:
        fig.update_yaxes(tickformat=".0%", range=[0, 1.05])
    return fig


def ver_tabla(df, titulo="Ver tabla", **kw):
    with st.expander(titulo):
        st.dataframe(df, hide_index=True, width="stretch", **kw)


# -- Colores y donas -------------------------------------------------------------------------------------
# Paleta categórica validada (orden fijo, nunca se "cicla" más allá de 8)
CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
# Estados (siempre acompañados de ícono + texto, nunca solo color)
BIEN, CERCA, LEJOS = "#0ca30c", "#fab219", "#d03b3b"
PISTA = "rgba(137,135,129,0.18)"   # el "fondo" de las donas


def estado_meta(indice):
    """indice = valor / meta. Devuelve (color, etiqueta)."""
    if indice is None or pd.isna(indice):
        return GRIS, "— sin dato"
    if indice >= 1:
        return BIEN, "✅ En meta"
    if indice >= 0.7:
        return CERCA, "⚠️ Cerca"
    return LEJOS, "🔴 Lejos"


def colores_por_nombre(nombres):
    """Color fijo por nombre (orden alfabético), para que no cambie al filtrar el ranking."""
    orden = sorted(set(nombres))
    return {n: CATEGORICA[i % len(CATEGORICA)] for i, n in enumerate(orden)}


def dona(fig, fraccion, color, centro, sub="", fila=None, col=None, nombre=""):
    """Agrega una dona tipo 'medidor' (fracción 0-1 rellena) a fig. Con fila/col va en una grilla."""
    f = 0.0 if fraccion is None or pd.isna(fraccion) else max(0.0, min(1.0, float(fraccion)))
    kw = dict(row=fila, col=col) if fila else {}
    fig.add_pie(values=[f, 1 - f], hole=0.72, sort=False, direction="clockwise", rotation=0,
                marker=dict(colors=[color, PISTA], line=dict(width=0)), textinfo="none",
                hoverinfo="skip", showlegend=False, name=nombre, **kw)
    return fig


def grilla_donas(items, columnas=4, alto_fila=210):
    """items: lista de dicts {titulo, fraccion, color, centro, sub}. Devuelve una figura con donas."""
    from plotly.subplots import make_subplots
    n = len(items)
    columnas = max(1, min(columnas, n))
    filas = -(-n // columnas)
    fig = make_subplots(rows=filas, cols=columnas, specs=[[{"type": "domain"}] * columnas] * filas,
                        subplot_titles=[it["titulo"] for it in items], vertical_spacing=0.16 / max(filas, 1) + 0.06)
    for i, it in enumerate(items):
        dona(fig, it["fraccion"], it["color"], it["centro"], fila=i // columnas + 1, col=i % columnas + 1)
    # Textos al centro de cada dona
    for i, it in enumerate(items):
        dom = fig.data[i].domain
        x = (dom.x[0] + dom.x[1]) / 2
        y = (dom.y[0] + dom.y[1]) / 2
        fig.add_annotation(x=x, y=y + 0.02 / filas, xref="paper", yref="paper", showarrow=False,
                           text=f"<b>{it['centro']}</b>", font=dict(size=20))
        if it.get("sub"):
            fig.add_annotation(x=x, y=y - 0.09 / filas, xref="paper", yref="paper", showarrow=False,
                               text=it["sub"], font=dict(size=11, color="#898781"))
    fig.update_layout(height=alto_fila * filas + 30, margin=dict(l=8, r=8, t=40, b=8), showlegend=False)
    for a in fig.layout.annotations[:n]:          # títulos de cada dona
        a.update(font=dict(size=13))
    return fig
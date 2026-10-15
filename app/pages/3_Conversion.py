"""Conversión de Airbnb: embudo por anuncio, comparación, cuellos de botella y tendencia."""
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] if Path(__file__).parent.name == "app" else Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import comun as c

c.configurar("Conversión en Airbnb")
if not c.conexion_ok() or not c.requiere("public.vw_conversion_fotos", "Ejecuta `sql/vw_scorecard.sql` en andina_lab."):
    st.stop()

fotos = c.leer("""SELECT propiedad, periodo_desde, periodo_hasta, fecha_captura, conversion_general,
                         impresiones_primera_pagina, busqueda_a_anuncio, anuncio_a_reserva, notas
                  FROM public.vw_conversion_fotos ORDER BY periodo_hasta, propiedad""")
if fotos.empty:
    st.info("Aún no hay capturas de conversión. Impórtalas en andina_lab con `importar_conversion_airbnb`.")
    st.stop()
for col in ("periodo_desde", "periodo_hasta", "fecha_captura"):
    fotos[col] = pd.to_datetime(fotos[col])

# Metas (parametros_conversion de andina_lab). La conversión general ideal = búsqueda→anuncio × anuncio→reserva.
par = c.leer("SELECT clave, valor FROM public.parametros_conversion")
ref = dict(zip(par["clave"], par["valor"].astype(float))) if not par.empty else {}
META = {"impresiones_primera_pagina": ref.get("ref_primera_pagina", 65.0),
        "busqueda_a_anuncio": ref.get("ref_busqueda_a_anuncio", 25.0),
        "anuncio_a_reserva": ref.get("ref_anuncio_a_reserva", 5.0)}
META["conversion_general"] = META["busqueda_a_anuncio"] * META["anuncio_a_reserva"] / 100
ETAPAS = [  # columna, nombre corto, pregunta
    ("impresiones_primera_pagina", "Visibilidad", "¿Apareces en la 1ª página?"),
    ("busqueda_a_anuncio", "Atractivo", "¿Hacen clic en tu anuncio?"),
    ("anuncio_a_reserva", "Cierre", "¿Reservan después de verlo?"),
]
CUELLO_COLOR = {"Visibilidad": c.CATEGORICA[0], "Atractivo": c.CATEGORICA[1], "Cierre": c.CATEGORICA[2],
                "Dentro de la meta": c.BIEN}


def etiqueta_foto(d, h, cap):
    t = f"{d:%d-%m-%Y} → {h:%d-%m-%Y}"
    return t + (f"  (capturado {cap:%d-%m})" if pd.notna(cap) else "")


def cuello(r):
    idx = {nombre: r[col] / META[col] for col, nombre, _ in ETAPAS if pd.notna(r[col]) and META[col]}
    if not idx:
        return None
    peor = min(idx, key=idx.get)
    return peor if idx[peor] < 1 else "Dentro de la meta"


# -- Filtros (barra lateral) --------------------------------------------------------------------------
with st.sidebar:
    st.header("Filtros")
    modo = st.radio("Ver por", ["Captura cargada", "Rango de fechas"],
                    help="Captura: una foto exacta tal como la copiaste de Airbnb. "
                         "Rango: todas las capturas cuyo período termina dentro de esas fechas.")
    capturas = (fotos[["periodo_desde", "periodo_hasta", "fecha_captura"]].drop_duplicates()
                .sort_values(["periodo_hasta", "periodo_desde"], ascending=False).reset_index(drop=True))
    if modo == "Captura cargada":
        i = st.selectbox("Captura", capturas.index,
                         format_func=lambda k: etiqueta_foto(*capturas.loc[k]))
        sel = capturas.loc[i]
        en_rango = fotos[(fotos["periodo_desde"] == sel["periodo_desde"]) & (fotos["periodo_hasta"] == sel["periodo_hasta"])]
        titulo_periodo = etiqueta_foto(*sel)
    else:
        lo, hi = fotos["periodo_hasta"].min().date(), max(fotos["periodo_hasta"].max().date(), date.today())
        rango = st.date_input("Período termina entre", (lo, hi), min_value=lo, max_value=hi, format="DD-MM-YYYY")
        d0, d1 = (rango if isinstance(rango, (tuple, list)) and len(rango) == 2 else (lo, hi))
        en_rango = fotos[fotos["periodo_hasta"].between(pd.Timestamp(d0), pd.Timestamp(d1))]
        titulo_periodo = f"capturas que terminan entre {d0:%d-%m-%Y} y {d1:%d-%m-%Y} (se usa la más reciente de cada anuncio)"
    todos = sorted(fotos["propiedad"].dropna().unique())
    anuncios = st.multiselect("Anuncios", todos, default=todos, placeholder="Elige anuncios")

if not anuncios:
    st.warning("Elige al menos un anuncio en la barra lateral.")
    st.stop()

# Una fila por anuncio: la captura elegida, o la más reciente del rango
actual = (en_rango[en_rango["propiedad"].isin(anuncios)]
          .sort_values("periodo_hasta").groupby("propiedad").tail(1).reset_index(drop=True))
if actual.empty:
    st.info("No hay capturas para esos filtros.")
    st.stop()
actual["cuello"] = actual.apply(cuello, axis=1)
st.caption(f"Mostrando: **{titulo_periodo}** · {len(actual)} anuncios.")

# -- 1. Tarjetas del portafolio ---------------------------------------------------------------------------
st.subheader("Portafolio")
tarjetas = [("conversion_general", "Conversión general", "de quienes te ven en la búsqueda, reservan")] + \
           [(col, f"{nom}", preg) for col, nom, preg in ETAPAS]
items = []
for col, nom, preg in tarjetas:
    prom = actual[col].mean()
    color, etiqueta = c.estado_meta(prom / META[col] if META[col] else None)
    bajo = int((actual[col] < META[col]).sum())
    items.append({"titulo": f"{nom}", "fraccion": prom / META[col] if META[col] else 0, "color": color,
                  "centro": f"{prom:.2f} %" if col == "conversion_general" else f"{prom:.1f} %",
                  "sub": f"meta {META[col]:.2f} %" if col == "conversion_general" else f"meta {META[col]:.0f} %",
                  "etiqueta": etiqueta, "bajo": bajo, "preg": preg})
st.plotly_chart(c.grilla_donas(items, columnas=4, alto_fila=230), width="stretch", config={"displayModeBar": False})
cols = st.columns(4)
for colu, it in zip(cols, items):
    colu.markdown(f"<div style='text-align:center'><b>{it['etiqueta']}</b><br>"
                  f"<span style='color:#898781;font-size:0.85em'>{it['preg']}<br>"
                  f"{it['bajo']} de {len(actual)} anuncios bajo la meta</span></div>", unsafe_allow_html=True)
st.caption("Cada dona muestra **cuánto de la meta alcanzas** (llena = meta cumplida); al centro, el promedio real. "
           "Metas en `parametros_conversion` (andina_lab).")

# -- 2. Embudo de un anuncio ---------------------------------------------------------------------------
st.divider()
st.subheader("Embudo por anuncio")
peor_primero = actual.sort_values("conversion_general")["propiedad"].tolist()
anuncio = st.selectbox("Anuncio", peor_primero, help="Ordenados de menor a mayor conversión.")
r = actual[actual["propiedad"] == anuncio].iloc[0]
izq, der = st.columns([3, 2], gap="large")
with izq:
    items_a = []
    for col, nom, preg in [("conversion_general", "Conversión general", "")] + ETAPAS:
        v = r[col]
        color, etiqueta = c.estado_meta(v / META[col] if pd.notna(v) and META[col] else None)
        items_a.append({"titulo": f"<b>{nom}</b>  {etiqueta}",
                        "fraccion": (v / META[col]) if pd.notna(v) else 0, "color": color,
                        "centro": "—" if pd.isna(v) else (f"{v:.2f} %" if col == "conversion_general" else f"{v:.1f} %"),
                        "sub": f"meta {META[col]:.2f} %" if col == "conversion_general" else f"meta {META[col]:.0f} %"})
    st.plotly_chart(c.grilla_donas(items_a, columnas=2, alto_fila=220), width="stretch",
                    config={"displayModeBar": False})
with der:
    # Embudo ilustrativo: de 1.000 personas que ven tu anuncio en la búsqueda
    base = 1000
    clics = base * (r["busqueda_a_anuncio"] or 0) / 100
    reservas = clics * (r["anuncio_a_reserva"] or 0) / 100
    fig = go.Figure(go.Funnel(
        y=["Te ven en la búsqueda", "Abren tu anuncio", "Reservan"], x=[base, clics, reservas],
        text=[f"{base:,.0f}".replace(",", "."), f"{clics:,.0f}".replace(",", "."), f"{reservas:.1f}".replace(".", ",")],
        textinfo="text", textposition="outside", textfont=dict(size=15),
        marker=dict(color=[c.CATEGORICA[0], c.CATEGORICA[1], c.CATEGORICA[2]]),
        connector=dict(line=dict(color=c.GRIS, width=1)),
        hovertemplate="%{y}: %{x:,.1f}<extra></extra>"))
    fig.update_layout(height=330, margin=dict(l=8, r=70, t=40, b=8), title=dict(text="Si 1.000 personas te ven…", font=dict(size=14)))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    meta_res = base * META["busqueda_a_anuncio"] / 100 * META["anuncio_a_reserva"] / 100
    st.markdown(f"Con las metas serían **{meta_res:.1f} reservas**. Cuello de botella: **{r['cuello'] or '—'}**.")
    if pd.notna(r.get("notas")) and str(r["notas"]).strip():
        st.caption(f"Notas: {r['notas']}")

# -- 3. Comparación entre anuncios ------------------------------------------------------------------------
st.divider()
st.subheader("Comparación entre anuncios")
st.caption("Verde = en meta · amarillo = sobre el 70 % de la meta · rojo = lejos. La línea punteada es la meta.")
tabs = st.tabs([f"{nom} · {preg}" for _, nom, preg in ETAPAS])
for tab, (col, nom, preg) in zip(tabs, ETAPAS):
    d = actual.dropna(subset=[col]).sort_values(col)
    d["color"] = d[col].map(lambda v: c.estado_meta(v / META[col])[0])
    d["estado"] = d[col].map(lambda v: c.estado_meta(v / META[col])[1])
    fig = go.Figure(go.Bar(x=d[col], y=d["propiedad"], orientation="h", marker_color=d["color"],
                           marker_line_width=0, text=[f"{v:.1f} %  {e}" for v, e in zip(d[col], d["estado"])],
                           textposition="outside", cliponaxis=False, customdata=d["estado"],
                           hovertemplate="%{y}: %{x:.1f} % · %{customdata}<extra></extra>"))
    fig.add_vline(x=META[col], line_dash="dot", line_color="#52514e", line_width=1.5,
                  annotation_text=f"meta {META[col]:.0f} %", annotation_position="top")
    fig.update_xaxes(range=[0, max(d[col].max(), META[col]) * 1.35], ticksuffix=" %")
    fig.update_layout(bargap=0.3)
    tab.plotly_chart(c.estilo_figura(fig, alto=80 + 36 * len(d), leyenda=False).update_layout(
        hovermode="closest", margin=dict(l=8, r=8, t=30, b=8)), width="stretch", config={"displayModeBar": False})

# -- 4. Cuellos de botella -------------------------------------------------------------------------------
st.divider()
izq, der = st.columns([2, 3], gap="large")
with izq:
    st.subheader("¿Dónde se pierden?")
    cu = actual["cuello"].value_counts().reindex(list(CUELLO_COLOR)).dropna().astype(int).reset_index()
    cu.columns = ["Cuello", "Anuncios"]
    fig = go.Figure(go.Pie(labels=cu["Cuello"], values=cu["Anuncios"], hole=0.6, sort=False,
                           marker=dict(colors=[CUELLO_COLOR[k] for k in cu["Cuello"]], line=dict(color="white", width=2)),
                           textinfo="value", textfont=dict(size=15, color="white"),
                           hovertemplate="%{label}: %{value} anuncios (%{percent})<extra></extra>"))
    fig.add_annotation(text=f"<b>{len(actual)}</b><br>anuncios", showarrow=False, font=dict(size=16))
    fig.update_layout(height=340, margin=dict(l=8, r=8, t=8, b=8),
                      legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center"))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
with der:
    st.subheader("Qué revisar en cada caso")
    consejos = {
        "Visibilidad": "Precio vs. competencia, estadía mínima, disponibilidad abierta, calificación.",
        "Atractivo": "Foto de portada, título y precio que se ve en la búsqueda.",
        "Cierre": "Precio final con tarifas, fotos interiores, descripción, reseñas recientes, reglas.",
    }
    for etapa, consejo in consejos.items():
        props = actual.loc[actual["cuello"] == etapa, "propiedad"].tolist()
        if props:
            st.markdown(f"<span style='color:{CUELLO_COLOR[etapa]};font-size:1.3em'>●</span> **{etapa}** "
                        f"({len(props)}): {', '.join(props)}  \n<span style='color:#898781'>{consejo}</span>",
                        unsafe_allow_html=True)
    ok = actual.loc[actual["cuello"] == "Dentro de la meta", "propiedad"].tolist()
    if ok:
        st.markdown(f"✅ **Dentro de la meta**: {', '.join(ok)}")

# -- 5. Tendencia -------------------------------------------------------------------------------------
st.divider()
st.subheader("Tendencia")
indicador = st.radio("Tasa", ["Conversión general", "Visibilidad (1ª página)", "Atractivo (búsqueda → anuncio)",
                              "Cierre (anuncio → reserva)"], horizontal=True)
col = {"Conversión general": "conversion_general", "Visibilidad (1ª página)": "impresiones_primera_pagina",
       "Atractivo (búsqueda → anuncio)": "busqueda_a_anuncio", "Cierre (anuncio → reserva)": "anuncio_a_reserva"}[indicador]
hist = fotos[fotos["propiedad"].isin(anuncios)].dropna(subset=[col])
if modo == "Rango de fechas":
    hist = hist[hist["propiedad"].isin(anuncios) & hist.index.isin(en_rango.index)]
if hist["periodo_hasta"].nunique() < 2:
    st.info("Con una sola captura aún no hay tendencia; sigue capturando cada mes.")
colores = c.colores_por_nombre(todos)
if len(anuncios) <= 4:
    fig = px.line(hist, x="periodo_hasta", y=col, color="propiedad", markers=True,
                  color_discrete_map=colores, labels={"propiedad": "Anuncio"})
    fig.update_traces(line_width=2.5, marker_size=9, hovertemplate="%{x|%d-%m-%Y}: %{y:.2f} %")
    fig.add_hline(y=META[col], line_dash="dot", line_color="#52514e", annotation_text="meta")
    st.plotly_chart(c.estilo_figura(fig, alto=380), width="stretch")
else:
    fig = px.line(hist, x="periodo_hasta", y=col, facet_col="propiedad", facet_col_wrap=4, markers=True,
                  color="propiedad", color_discrete_map=colores)
    fig.update_traces(line_width=2.5, marker_size=8, hovertemplate="%{x|%d-%m-%Y}: %{y:.2f} %<extra></extra>")
    fig.add_hline(y=META[col], line_dash="dot", line_color="#52514e", line_width=1)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_yaxes(matches=None, showticklabels=True, rangemode="tozero")
    filas = -(-hist["propiedad"].nunique() // 4)
    st.plotly_chart(c.estilo_figura(fig, alto=60 + 210 * filas, leyenda=False).update_layout(hovermode="closest"),
                    width="stretch")
    st.caption("Elige 4 anuncios o menos para verlos juntos en un solo gráfico. Línea punteada = meta.")

c.ver_tabla(hist.assign(periodo_desde=hist["periodo_desde"].dt.date, periodo_hasta=hist["periodo_hasta"].dt.date,
                        fecha_captura=hist["fecha_captura"].dt.date)
            [["propiedad", "periodo_desde", "periodo_hasta", "fecha_captura", "conversion_general",
              "impresiones_primera_pagina", "busqueda_a_anuncio", "anuncio_a_reserva", "notas"]],
            "Ver todas las capturas (tabla)")

# -- 6. Acciones -----------------------------------------------------------------------------------------
if c.existe("public.vw_acciones_impacto"):
    acc = c.leer("SELECT * FROM public.vw_acciones_impacto")
    if "propiedad" in acc.columns:
        acc = acc[acc["propiedad"].isin(anuncios)]
    if not acc.empty:
        st.divider()
        st.subheader("Acciones registradas y su efecto")
        st.dataframe(acc, hide_index=True, width="stretch")
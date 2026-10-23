"""Reviews: estado por propiedad, evolución, categorías y temas (IA)."""
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

c.configurar("Reviews")
if not c.conexion_ok() or not c.requiere("public.vw_reviews_actual", c.COMO_ACTUALIZAR):
    st.stop()

# -- Estado ---------------------------------------------------------------------------------------
st.subheader("Estado actual")
st.caption("Crítico: acumulado < 4,80, promedio 3 meses < 4,70 o una review ≤ 3 este mes. "
           "Alerta: acumulado < 4,90 o 3 meses < 4,85.")
rv = c.leer("SELECT * FROM public.vw_reviews_actual")
orden = {"Crítico": 0, "Alerta": 1, "OK": 2, "Sin datos suficientes": 3}
rv = rv.assign(o=rv["criticidad"].map(orden)).sort_values(["o", "promedio_acumulado"])
rv["Estado"] = rv["criticidad"].map(c.ESTADO).fillna(rv["criticidad"])
st.dataframe(
    rv[["propiedad", "Estado", "promedio_acumulado", "reviews_acumuladas", "promedio_3m", "reviews_3m",
        "reviews_mes", "peor_categoria_3m", "peor_nota_3m", "motivo"]],
    hide_index=True, width="stretch",
    column_config={"propiedad": "Propiedad", "promedio_acumulado": st.column_config.NumberColumn("Acumulado", format="%.2f"),
                   "reviews_acumuladas": "N° reviews", "promedio_3m": st.column_config.NumberColumn("3 meses", format="%.2f"),
                   "reviews_3m": "N° 3 meses", "reviews_mes": "Este mes", "peor_categoria_3m": "Peor categoría 3m",
                   "peor_nota_3m": st.column_config.NumberColumn("Nota", format="%.2f"), "motivo": "Motivo"})

# -- Categorías (últimos 3 meses) -------------------------------------------------------------------------
st.subheader("Notas por categoría · últimos 3 meses")
cat = c.leer("""
    SELECT propiedad,
           SAFE_DIVIDE(SUM(s_limpieza), SUM(c_limpieza))          AS limpieza,
           SAFE_DIVIDE(SUM(s_exactitud), SUM(c_exactitud))        AS exactitud,
           SAFE_DIVIDE(SUM(s_checkin), SUM(c_checkin))            AS checkin,
           SAFE_DIVIDE(SUM(s_comunicacion), SUM(c_comunicacion))  AS comunicacion,
           SAFE_DIVIDE(SUM(s_ubicacion), SUM(c_ubicacion))        AS ubicacion,
           SAFE_DIVIDE(SUM(s_valor), SUM(c_valor))                AS valor,
           SUM(reviews)                                           AS reviews
    FROM public.vw_reviews_mensual
    WHERE CAST(mes AS DATE) >= DATE_SUB(DATE_TRUNC(CURRENT_DATE('America/Santiago'), MONTH), INTERVAL 2 MONTH)
    GROUP BY propiedad ORDER BY propiedad""")
if not cat.empty:
    nota = lambda t: st.column_config.ProgressColumn(t, format="%.2f", min_value=4.0, max_value=5.0)  # noqa: E731
    st.dataframe(cat, hide_index=True, width="stretch",
                 column_config={"propiedad": "Propiedad", "limpieza": nota("Limpieza"), "exactitud": nota("Exactitud"),
                                "checkin": nota("Check-in"), "comunicacion": nota("Comunicación"),
                                "ubicacion": nota("Ubicación"), "valor": nota("Calidad-precio"), "reviews": "Reviews"})

# -- Temas con IA -------------------------------------------------------------------------------------
st.subheader("Qué dicen los comentarios (clasificado con IA)")


def temas_ia():
    if not c.requiere("analitica.vw_pendientes_propiedad", c.COMO_ACTUALIZAR):
        return
    n_temas = c.leer("SELECT COUNT(*) AS n FROM analitica.review_temas")["n"].iloc[0]
    if n_temas == 0:
        st.info("Aún no hay reviews clasificadas. Corre `python -m analitica.reviews_ia --limite 5` para probar.")
        return

    props = ["Todas"] + sorted(c.leer("SELECT DISTINCT propiedad FROM analitica.vw_review_temas_detalle "
                                      "WHERE propiedad IS NOT NULL")["propiedad"])
    prop = st.selectbox("Propiedad", props)
    filtro = "" if prop == "Todas" else "AND propiedad = @p"
    params = {} if prop == "Todas" else {"p": prop}

    temas = c.leer(f"""
        SELECT tema,
               COUNTIF(sentimiento IN ('negativo', 'neutro')) AS quejas,
               COUNTIF(sentimiento = 'positivo')              AS elogios
        FROM analitica.vw_review_temas_detalle
        WHERE CAST(fecha AS DATE) >= DATE_SUB(CURRENT_DATE('America/Santiago'), INTERVAL 90 DAY) {filtro}
        GROUP BY tema""", params)
    if not temas.empty:
        temas["Tema"] = temas["tema"].map(c.NOMBRE_TEMA).fillna(temas["tema"])
        larga = temas.melt(id_vars="Tema", value_vars=["quejas", "elogios"], var_name="Tipo", value_name="Menciones")
        larga["Tipo"] = larga["Tipo"].map({"quejas": "Quejas y sugerencias", "elogios": "Elogios"})
        orden_t = temas.sort_values(["quejas", "elogios"])["Tema"].tolist()
        fig = px.bar(larga, x="Menciones", y="Tema", color="Tipo", orientation="h", barmode="group",
                     category_orders={"Tema": orden_t[::-1], "Tipo": ["Quejas y sugerencias", "Elogios"]},
                     color_discrete_map={"Quejas y sugerencias": c.NARANJO, "Elogios": c.AZUL})
        fig.update_layout(bargap=0.3, bargroupgap=0.1)
        st.plotly_chart(c.estilo_figura(fig, alto=100 + 40 * len(temas)).update_layout(hovermode="y unified"),
                        width="stretch")
        st.caption("Últimos 90 días.")
        c.ver_tabla(temas[["Tema", "quejas", "elogios"]].rename(columns={"quejas": "Quejas", "elogios": "Elogios"}))

    st.markdown("**Pendientes por corregir** (últimos 90 días, ordenados por prioridad = suma de severidades)")
    pend = c.leer(f"""SELECT propiedad, tema, menciones, prioridad, severidad_maxima, ultima_mencion,
                             en_comentario_privado, citas, acciones_sugeridas
                      FROM analitica.vw_pendientes_propiedad WHERE TRUE {filtro}
                      ORDER BY prioridad DESC, ultima_mencion DESC""", params)
    if pend.empty:
        st.markdown("Sin quejas en los últimos 90 días. 🎉")
    else:
        pend["tema"] = pend["tema"].map(c.NOMBRE_TEMA).fillna(pend["tema"])
        pend["citas"] = pend["citas"].map(lambda x: " · ".join(f"“{t}”" for t in (x or [])))
        pend["acciones_sugeridas"] = pend["acciones_sugeridas"].map(lambda x: " · ".join(x or []))
        st.dataframe(pend, hide_index=True, width="stretch",
                     column_config={"propiedad": "Propiedad", "tema": "Tema", "menciones": "Menciones",
                                    "prioridad": "Prioridad", "severidad_maxima": "Severidad máx.",
                                    "ultima_mencion": st.column_config.DateColumn("Última", format="DD-MM-YYYY"),
                                    "en_comentario_privado": "En privado", "citas": st.column_config.TextColumn("Citas", width="large"),
                                    "acciones_sugeridas": st.column_config.TextColumn("Acciones sugeridas", width="large")})

    st.markdown("**Fortalezas** (lo que más elogian: úsalo en el título y la descripción del anuncio)")
    fort = c.leer(f"""SELECT propiedad, tema, menciones, citas FROM analitica.vw_fortalezas_propiedad
                      WHERE TRUE {filtro} ORDER BY menciones DESC LIMIT 30""", params)
    if not fort.empty:
        fort["tema"] = fort["tema"].map(c.NOMBRE_TEMA).fillna(fort["tema"])
        fort["citas"] = fort["citas"].map(lambda x: " · ".join(f"“{t}”" for t in (x or [])))
        st.dataframe(fort, hide_index=True, width="stretch",
                     column_config={"propiedad": "Propiedad", "tema": "Tema", "menciones": "Menciones",
                                    "citas": st.column_config.TextColumn("Citas", width="large")})


temas_ia()

# -- Evolución (al final: es contexto, lo accionable va arriba) ----------------------------------------
st.subheader("Nota general por mes")
rm = c.leer("""SELECT propiedad, mes, reviews_con_nota AS reviews, general, nota_minima, reviews_bajo_5
               FROM public.vw_reviews_mensual WHERE reviews_con_nota > 0 ORDER BY mes""")
if rm.empty:
    st.info("Aún no hay reviews con nota.")
else:
    rm["mes"] = pd.to_datetime(rm["mes"])
    rm["Mes"] = rm["mes"].map(c.nombre_mes)
    meses = [c.nombre_mes(m) for m in sorted(rm["mes"].unique())]
    # Mismo orden que "Estado actual": las que necesitan atención, arriba
    filas = [p for p in rv["propiedad"] if p in set(rm["propiedad"])]
    filas += sorted(set(rm["propiedad"]) - set(filas))

    # Casi todas las notas están entre 4,5 y 5: la escala de colores se concentra ahí y cada celda lleva su número.
    # Naranjo bajo 4,80 (umbral de Crítico) · neutro entre 4,80 y 4,90 · azul desde 4,90.
    piso, techo = 4.5, 5.0
    pos = lambda v: (v - piso) / (techo - piso)  # noqa: E731
    escala = [[0, c.NARANJO], [pos(4.8), "#f8cdb9"], [pos(4.85), "#efeee8"], [pos(4.9), c.SECUENCIAL[0]],
              [1, c.AZUL_CLARO]]
    nota = rm.pivot(index="propiedad", columns="Mes", values="general").reindex(index=filas, columns=meses)
    extra = rm.pivot(index="propiedad", columns="Mes", values=["reviews", "reviews_bajo_5", "nota_minima"])
    datos = [[[extra.get(("reviews", m), {}).get(p), extra.get(("reviews_bajo_5", m), {}).get(p),
               extra.get(("nota_minima", m), {}).get(p)] for m in meses] for p in filas]
    texto = nota.map(lambda v: "" if pd.isna(v) else f"{v:.2f}".replace(".", ","))
    fig = go.Figure(go.Heatmap(
        z=nota.clip(lower=piso).values, x=meses, y=filas, zmin=piso, zmax=techo, colorscale=escala,
        text=texto.values, texttemplate="%{text}", textfont=dict(size=13, color="#1d1d1b"),
        customdata=datos, xgap=3, ygap=3, hoverongaps=False,
        colorbar=dict(title="", tickvals=[4.5, 4.8, 4.9, 5.0], ticktext=["≤4,5", "4,8", "4,9", "5,0"], thickness=12),
        hovertemplate="<b>%{y}</b> · %{x}<br>Nota %{text} con %{customdata[0]} reviews"
                      "<br>Bajo 5: %{customdata[1]} · Mínima: %{customdata[2]}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    fig.update_xaxes(side="top")
    st.plotly_chart(c.estilo_figura(fig, alto=80 + 34 * len(filas), leyenda=False).update_layout(hovermode="closest"),
                    width="stretch")
    st.caption("Cada celda es el promedio de las reviews del mes. Naranjo: bajo 4,80 (umbral de Crítico del "
               "acumulado) · tonos claros: 4,80–4,90 (Alerta) · azul: 4,90 o más. Vacío = sin reviews ese mes. "
               "Pasa el mouse para ver cuántas reviews y la nota mínima.")

    # Detalle de una propiedad: eje ajustado a sus notas para ver diferencias de décimas
    sel = st.selectbox("Ver una propiedad en detalle", filas, key="detalle_nota")
    g = rm[rm["propiedad"] == sel]
    abajo = min(4.6, float(g["general"].min()) - 0.1)
    fig = go.Figure()
    fig.add_hrect(y0=abajo, y1=4.8, fillcolor=c.NARANJO, opacity=0.08, line_width=0)
    fig.add_hline(y=4.8, line_dash="dot", line_color=c.NARANJO, line_width=1,
                  annotation_text="4,80 Crítico", annotation_position="bottom left")
    fig.add_hline(y=4.9, line_dash="dot", line_color=c.GRIS, line_width=1,
                  annotation_text="4,90 Alerta", annotation_position="top left")
    fig.add_scatter(x=g["mes"], y=g["general"], mode="lines+markers+text", line=dict(color=c.AZUL, width=2),
                    marker=dict(size=10, color=[c.NARANJO if v < 4.8 else c.AZUL for v in g["general"]]),
                    text=[f"{v:.2f}".replace(".", ",") for v in g["general"]], textposition="top center",
                    customdata=g[["reviews", "reviews_bajo_5", "nota_minima"]],
                    hovertemplate="%{x|%b %Y}: %{y:.2f} con %{customdata[0]} reviews · bajo 5: %{customdata[1]}"
                                  " · mínima: %{customdata[2]}<extra></extra>")
    fig.update_yaxes(range=[abajo, 5.08], dtick=0.1, tickformat=".1f")
    fig.update_xaxes(dtick="M1", tickformat="%b %Y")
    st.plotly_chart(c.estilo_figura(fig, alto=340, leyenda=False).update_layout(hovermode="closest", separators=",."),
                    width="stretch")
    c.ver_tabla(rm[["propiedad", "Mes", "reviews", "general", "reviews_bajo_5", "nota_minima"]].rename(
        columns={"propiedad": "Propiedad", "reviews": "Reviews", "general": "Nota general",
                 "reviews_bajo_5": "Bajo 5", "nota_minima": "Mínima"}))

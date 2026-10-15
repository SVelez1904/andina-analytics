"""Reviews: estado por propiedad, evolución, categorías y temas (IA)."""
import pandas as pd
import plotly.express as px
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

# -- Evolución --------------------------------------------------------------------------------------
st.subheader("Nota general por mes")
rm = c.leer("""SELECT propiedad, mes, reviews, general FROM public.vw_reviews_mensual
               WHERE reviews_con_nota > 0 ORDER BY mes""")
if rm.empty:
    st.info("Aún no hay reviews con nota.")
else:
    rm["mes"] = pd.to_datetime(rm["mes"])
    fig = px.line(rm, x="mes", y="general", facet_col="propiedad", facet_col_wrap=4, markers=True,
                  color_discrete_sequence=[c.AZUL], custom_data=["reviews"])
    fig.update_traces(line_width=2, marker_size=8,
                      hovertemplate="%{x|%b %Y}: %{y:.2f} (%{customdata[0]} reviews)<extra></extra>")
    fig.add_hline(y=4.8, line_dash="dot", line_color=c.GRIS, line_width=1)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_yaxes(range=[3.9, 5.05])
    filas = -(-rm["propiedad"].nunique() // 4)
    st.plotly_chart(c.estilo_figura(fig, alto=60 + 210 * filas, leyenda=False).update_layout(hovermode="closest"),
                    width="stretch")
    st.caption("Línea punteada: 4,80 (umbral de Crítico para el acumulado).")
    c.ver_tabla(rm.assign(mes=rm["mes"].dt.strftime("%Y-%m")).rename(
        columns={"propiedad": "Propiedad", "mes": "Mes", "reviews": "Reviews", "general": "Nota general"}))

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
if not c.requiere("analitica.vw_pendientes_propiedad", c.COMO_ACTUALIZAR):
    st.stop()
n_temas = c.leer("SELECT COUNT(*) AS n FROM analitica.review_temas")["n"].iloc[0]
if n_temas == 0:
    st.info("Aún no hay reviews clasificadas. Corre `python -m analitica.reviews_ia --limite 5` para probar.")
    st.stop()

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

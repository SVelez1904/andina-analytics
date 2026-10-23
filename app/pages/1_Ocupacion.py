"""Ocupación, ADR y RevPAR; pronóstico y noches libres. Con filtros por fechas y anuncio."""
import sys
from pathlib import Path

# Raíz del repo en la ruta de Python ANTES de importar comun/analitica (necesario en Streamlit Cloud)
RAIZ = Path(__file__).resolve().parents[1] if Path(__file__).parent.name == "app" else Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import comun as c
from analitica.config import CONFIABLE_DESDE

c.configurar("Ocupación y pronóstico")
if not c.conexion_ok() or not c.requiere("public.vw_fct_noches", c.COMO_ACTUALIZAR):
    st.stop()

# Ocupación del MES COMPLETO ("on the books"): cuenta las noches ya ocurridas y las futuras que ya
# están reservadas, sobre todas las noches del mes. El mes en curso y los futuros todavía pueden subir.
# SQL en dialecto BigQuery. "hoy" se toma en hora de Chile.
SQL_MES_COMPLETO = """
WITH params AS (
    SELECT @hoy AS hoy                   -- hoy en Chile, desde Python (c.hoy())
),
vendidas AS (                            -- una fila por propiedad y noche vendida (sin duplicar solapes)
    SELECT id_propriedade, fecha,
           SUM(ingreso_noche_local) AS ingreso_local, SUM(ingreso_noche_clp) AS ingreso_clp
    FROM public.vw_fct_noches WHERE vendida
    GROUP BY id_propriedade, fecha
),
props AS (
    SELECT n.id_propriedade, MIN(n.fecha) AS alta, MIN(n.moneda_local) AS moneda_local, pf.fecha_baja
    FROM public.vw_fct_noches n
    LEFT JOIN public.propiedad_fechas pf ON pf.id_propriedade = n.id_propriedade
    GROUP BY n.id_propriedade, pf.fecha_baja
),
horizonte AS (                           -- hasta fin del mes de la última noche vendida (mín. 60 días)
    SELECT LAST_DAY(GREATEST(COALESCE(MAX(v.fecha), ANY_VALUE(p.hoy)),
                             DATE_ADD(ANY_VALUE(p.hoy), INTERVAL 60 DAY)), MONTH) AS fin
    FROM params p LEFT JOIN vendidas v ON TRUE
),
calendario AS (                          -- todas las noches, de alta a baja
    SELECT p.id_propriedade, p.moneda_local, fecha,
           DATE_TRUNC(fecha, MONTH) AS mes,
           CASE WHEN DATE_TRUNC(fecha, MONTH) < DATE_TRUNC(k.hoy, MONTH) THEN 'cerrado'
                WHEN DATE_TRUNC(fecha, MONTH) = DATE_TRUNC(k.hoy, MONTH) THEN 'en curso'
                ELSE 'futuro' END AS estado_mes,
           fecha >= k.hoy AS es_futura
    FROM props p
    CROSS JOIN horizonte h
    CROSS JOIN params k
    CROSS JOIN UNNEST(GENERATE_DATE_ARRAY(
        p.alta,
        LEAST(COALESCE(DATE_SUB(p.fecha_baja, INTERVAL 1 DAY), h.fin), h.fin)
    )) AS fecha
)
SELECT pr.nome_anuncio                                                  AS propiedad,
       CASE c.moneda_local WHEN 'BRL' THEN 'Brasil' ELSE 'Chile' END    AS mercado,
       c.moneda_local                                                   AS moneda_local,
       c.mes                                                            AS mes,
       c.estado_mes                                                     AS estado_mes,
       COUNT(*)                                                         AS noches_disponibles,
       COUNT(v.fecha)                                                   AS noches_vendidas,
       COUNTIF(v.fecha IS NOT NULL AND c.es_futura)                     AS noches_futuras_vendidas,
       COUNTIF(NOT c.es_futura)                                         AS noches_pasadas,
       COALESCE(SUM(v.ingreso_local), 0)                                AS ingreso_alojamiento,
       COALESCE(SUM(v.ingreso_clp), 0)                                  AS ingreso_alojamiento_clp
FROM calendario c
JOIN public.dim_propiedades pr ON pr.id_interno = c.id_propriedade
LEFT JOIN vendidas v ON v.id_propriedade = c.id_propriedade AND v.fecha = c.fecha
GROUP BY 1, 2, 3, 4, 5
ORDER BY mes
"""
kp = c.leer(SQL_MES_COMPLETO, {"hoy": c.hoy()})
if kp.empty:
    st.info("Aún no hay datos de ocupación.")
    st.stop()
kp["mes"] = pd.to_datetime(kp["mes"])
todos = sorted(kp["propiedad"].dropna().unique())
colores = c.colores_por_nombre(todos)
hoy_mes = pd.Timestamp.today().normalize().replace(day=1)

# -- Filtros (barra lateral) ----------------------------------------------------------------------------
with st.sidebar:
    st.header("Filtros")
    meses = sorted(kp["mes"].unique())
    actual = next((m for m in meses if pd.Timestamp(m) == hoy_mes), meses[-1])

    st.markdown("### Período")
    tipo_filtro = st.radio("Modo de selección", ["Mes único", "Rango de meses"], horizontal=True,
                           label_visibility="collapsed")

    if tipo_filtro == "Mes único":
        mes_seleccionado = st.selectbox(
            "Mes",
            options=meses,
            index=meses.index(actual),
            format_func=c.nombre_mes,
        )
        desde = hasta = mes_seleccionado
    else:
        c1, c2 = st.columns(2)
        with c1:
            desde = st.selectbox(
                "Desde",
                options=meses,
                index=meses.index(actual),
                format_func=c.nombre_mes,
            )
        with c2:
            # Asegurar que 'hasta' sea mayor o igual a 'desde'
            meses_hasta = [m for m in meses if m >= desde]
            hasta = st.selectbox(
                "Hasta",
                options=meses_hasta,
                index=len(meses_hasta) - 1,
                format_func=c.nombre_mes,
            )

    st.markdown("---")
    anuncios = st.multiselect("Anuncios", todos, default=todos, placeholder="Elige anuncios")
    st.caption("Filtra por mes individual o un rango personalizado de fechas.")

if not anuncios:
    st.warning("Elige al menos un anuncio en la barra lateral.")
    st.stop()

f = kp[kp["propiedad"].isin(anuncios) & kp["mes"].between(desde, hasta)]
periodo = c.nombre_mes(desde) if desde == hasta else f"{c.nombre_mes(desde)} a {c.nombre_mes(hasta)}"
st.caption(f"Período: **{periodo}** · {len(anuncios)} anuncios · **mes completo**: noches ya ocurridas + noches "
           "futuras ya reservadas, sobre todas las noches del mes.")
if (f["estado_mes"] != "cerrado").any():
    futuras = int(f["noches_futuras_vendidas"].sum())
    st.info(f"Incluye meses que aún no terminan: {futuras} de las noches vendidas son futuras (ya reservadas). "
            "Estos números todavía pueden subir con nuevas reservas, o bajar si hay cancelaciones.", icon="📅")


def agregar(df, por):
    g = df.groupby(por, as_index=False).agg(vendidas=("noches_vendidas", "sum"), disponibles=("noches_disponibles", "sum"),
                                            futuras=("noches_futuras_vendidas", "sum"), pasadas=("noches_pasadas", "sum"),
                                            ingreso=("ingreso_alojamiento", "sum"), ingreso_clp=("ingreso_alojamiento_clp", "sum"))
    g["ocupacion"] = g["vendidas"] / g["disponibles"]
    g["adr"] = g["ingreso"] / g["vendidas"].where(g["vendidas"] > 0)
    g["revpar"] = g["ingreso"] / g["disponibles"]
    return g


# -- 1. Resumen del período por mercado ---------------------------------------------------------------------
st.subheader("Resumen del período")
mer = c.chile_primero(agregar(f, ["mercado", "moneda_local"]), ["mercado"])
for _, m in mer.iterrows():
    mon = m["moneda_local"]
    st.markdown(f"**{m['mercado']}**")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Ocupación", c.pct(m["ocupacion"]))
    k2.metric(f"ADR ({mon})", c.dinero(m["adr"]))
    k3.metric(f"RevPAR ({mon})", c.dinero(m["revpar"]))
    k4.metric("Noches vendidas", f"{int(m['vendidas'])} de {int(m['disponibles'])}")

# -- KPI financiero: ingresos vs meta (todo el portafolio, no depende del filtro de anuncios) -----------------
st.subheader("Ingresos vs meta")
meta = c.META_INGRESO_MENSUAL_CLP
im = kp[kp["mes"].between(desde, hasta)].groupby("mes", as_index=False).agg(
    ingreso_clp=("ingreso_alojamiento_clp", "sum"))
im["cumplimiento"] = im["ingreso_clp"] / meta
im[["color", "estado"]] = im["cumplimiento"].map(c.estado_meta).tolist()
tot, meta_periodo = im["ingreso_clp"].sum(), meta * len(im)
k1, k2, k3 = st.columns(3)
k1.metric("Ingreso del período (CLP)", c.dinero(tot))
k2.metric(f"Meta ({len(im)} {'mes' if len(im) == 1 else 'meses'} × {meta / 1e6:.0f} M)".replace(".", ","),
          c.dinero(meta_periodo))
k3.metric("Cumplimiento", c.pct(tot / meta_periodo), c.estado_meta(tot / meta_periodo)[1], delta_color="off")
if len(im) > 1:
    fig = go.Figure(go.Bar(x=im["mes"], y=im["ingreso_clp"], marker_color=im["color"], customdata=im[["estado"]],
                           text=im["cumplimiento"].map(c.pct), textposition="outside", cliponaxis=False,
                           hovertemplate="%{x|%b %Y}: %{y:,.0f} CLP · %{text} de la meta (%{customdata[0]})<extra></extra>"))
    fig.add_hline(y=meta, line_dash="dot", line_color="#52514e", line_width=1.5,
                  annotation_text=f"meta {meta / 1e6:.0f} M", annotation_position="top left")
    fig.update_xaxes(dtick="M1", tickformat="%b %Y")
    fig.update_yaxes(range=[0, max(im["ingreso_clp"].max(), meta) * 1.15])
    st.plotly_chart(c.estilo_figura(fig, alto=300, leyenda=False), width="stretch", config={"displayModeBar": False})
st.caption(f"Meta de {c.dinero(meta, 'CLP')} al mes de ingreso por alojamiento, para **todo el portafolio** "
           "(Brasil convertido a CLP; no cambia con el filtro de anuncios). Verde = en meta · amarillo = sobre el "
           "70 % · rojo = lejos. Los meses en curso y futuros incluyen noches ya reservadas y pueden subir.")

# -- 2. Donas por anuncio -------------------------------------------------------------------------------
st.subheader("Ocupación por anuncio")
pa = agregar(f, ["propiedad", "mercado", "moneda_local"]).sort_values("ocupacion", ascending=False)
items = [{"titulo": r.propiedad if len(r.propiedad) <= 22 else r.propiedad[:20] + "…",
          "fraccion": r.ocupacion, "color": colores[r.propiedad], "centro": c.pct(r.ocupacion),
          "sub": f"{int(r.vendidas)}/{int(r.disponibles)}" + (f" · {int(r.futuras)} fut." if r.futuras else "")} for r in pa.itertuples()]
st.plotly_chart(c.grilla_donas(items, columnas=5, alto_fila=200), width="stretch", config={"displayModeBar": False})
st.caption("Cada dona: parte coloreada = noches vendidas del mes completo (incluye las futuras ya reservadas, "
           "«fut.»); gris = noches libres. Ordenadas de mayor a menor ocupación.")

izq, der = st.columns(2, gap="large")
with izq:
    st.markdown("**Noches del período**")
    tot_v, tot_d = int(pa["vendidas"].sum()), int(pa["disponibles"].sum())
    fut, pas = int(pa["futuras"].sum()), int(pa["pasadas"].sum())
    partes = [("Vendidas (ya ocurridas)", tot_v - fut, c.AZUL), ("Reservadas (futuras)", fut, c.AZUL_CLARO),
              ("Libres que ya pasaron", pas - (tot_v - fut), c.GRIS), ("Libres por vender", (tot_d - pas) - fut, c.PISTA)]
    partes = [p_ for p_ in partes if p_[1] > 0]
    fig = go.Figure(go.Pie(labels=[f"{n}: {v}" for n, v, _ in partes], values=[v for _, v, _ in partes], hole=0.62,
                           sort=False, marker=dict(colors=[col_ for *_, col_ in partes], line=dict(color="white", width=2)),
                           textinfo="percent", hovertemplate="%{label} noches (%{percent})<extra></extra>"))
    fig.add_annotation(text=f"<b>{c.pct(tot_v / tot_d if tot_d else None)}</b><br>ocupación", showarrow=False,
                       font=dict(size=16))
    fig.update_layout(height=380, margin=dict(l=8, r=8, t=8, b=8),
                      legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center"))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
with der:
    st.markdown("**Quién aporta el ingreso** (en CLP; Brasil convertido al tipo de cambio)")
    ing = pa[pa["ingreso_clp"] > 0].sort_values("ingreso_clp", ascending=False)
    if ing.empty:
        st.info("Sin ingresos en el período.")
    else:
        top = ing.head(7)
        resto = ing.iloc[7:]["ingreso_clp"].sum()
        labels, values = list(top["propiedad"]), list(top["ingreso_clp"])
        cols_ = [colores[p] for p in labels]          # mismo color que en las donas de arriba
        if resto > 0:
            labels.append("Otros")
            values.append(resto)
            cols_.append(c.GRIS)
        fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.62, sort=False,
                               marker=dict(colors=cols_, line=dict(color="white", width=2)), textinfo="percent",
                               textfont=dict(color="white"),
                               hovertemplate="%{label}: %{value:,.0f} CLP (%{percent})<extra></extra>"))
        fig.add_annotation(text=f"<b>{sum(values) / 1e6:.1f} M</b><br>CLP".replace('.', ','), showarrow=False, font=dict(size=16))
        fig.update_layout(height=380, margin=dict(l=8, r=8, t=8, b=8),
                          legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center", font=dict(size=11)))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

c.ver_tabla(pa[["propiedad", "mercado", "ocupacion", "adr", "revpar", "vendidas", "futuras", "disponibles", "ingreso", "ingreso_clp"]],
            column_config={"ocupacion": st.column_config.NumberColumn("Ocupación", format="percent"),
                           "adr": st.column_config.NumberColumn("ADR (moneda local)", format="%.0f"),
                           "revpar": st.column_config.NumberColumn("RevPAR (moneda local)", format="%.0f"),
                           "ingreso": st.column_config.NumberColumn("Ingreso (moneda local)", format="%.0f"),
                           "ingreso_clp": st.column_config.NumberColumn("Ingreso CLP", format="%.0f")})

# -- 3. Evolución mensual ---------------------------------------------------------------------------------
st.subheader("Evolución mensual")
metrica = st.radio("Indicador", ["Ocupación", "ADR", "RevPAR"], horizontal=True, label_visibility="collapsed")
col = {"Ocupación": "ocupacion", "ADR": "adr", "RevPAR": "revpar"}[metrica]
por_anuncio = st.toggle("Separar por anuncio", value=len(anuncios) <= 4,
                        help="Con más de 4 anuncios se muestra un gráfico pequeño por anuncio.")
if por_anuncio:
    ev = agregar(f, ["propiedad", "mercado", "moneda_local", "mes"])
    if len(anuncios) <= 4:
        fig = px.line(ev, x="mes", y=col, color="propiedad", markers=True, color_discrete_map=colores,
                      labels={"propiedad": "Anuncio"})
        fig.update_traces(line_width=2.5, marker_size=9)
        alto = 380
    else:
        fig = px.line(ev, x="mes", y=col, color="propiedad", facet_col="propiedad", facet_col_wrap=5,
                      markers=True, color_discrete_map=colores)
        fig.update_traces(line_width=2.5, marker_size=7)
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        fig.update_yaxes(showticklabels=True)
        alto = 60 + 190 * -(-len(anuncios) // 5)
    fig.update_traces(hovertemplate="%{x|%b %Y}: " + ("%{y:.0%}" if col == "ocupacion" else "%{y:,.0f}") + "<extra></extra>")
    fig.update_xaxes(dtick="M1", tickformat="%b %Y")
    st.plotly_chart(c.estilo_figura(fig, alto=alto, y_pct=col == "ocupacion", leyenda=len(anuncios) <= 4)
                    .update_layout(hovermode="closest"), width="stretch")
    if col != "ocupacion":
        st.caption("ADR y RevPAR en la moneda de cada anuncio (CLP o BRL).")
else:
    ev = agregar(f, ["mercado", "moneda_local", "mes"])
    if col == "ocupacion":
        fig = px.line(ev, x="mes", y=col, color="mercado", markers=True, color_discrete_map=c.COLOR_MERCADO,
                      category_orders={"mercado": c.ORDEN_MERCADOS}, labels={"mercado": "Mercado"})
        fig.update_traces(line_width=2.5, marker_size=9, hovertemplate="%{y:.0%}")
        fig.update_xaxes(dtick="M1", tickformat="%b %Y")
        st.plotly_chart(c.estilo_figura(fig, y_pct=True, leyenda=ev["mercado"].nunique() > 1), width="stretch")
    else:
        # En moneda local: un gráfico por mercado (nunca dos escalas en un mismo eje)
        mercados = list(c.chile_primero(ev, ["mercado"])["mercado"].unique())
        for colu, mercado in zip(st.columns(len(mercados)), mercados):
            g = ev[ev["mercado"] == mercado]
            mon = g["moneda_local"].iloc[0]
            fig = px.line(g, x="mes", y=col, markers=True, title=f"{mercado} ({mon})",
                          color_discrete_sequence=[c.COLOR_MERCADO.get(mercado, c.AZUL)])
            fig.update_traces(line_width=2.5, marker_size=9, hovertemplate="%{y:,.0f} " + mon)
            fig.update_xaxes(dtick="M1", tickformat="%b %Y")
            colu.plotly_chart(c.estilo_figura(fig, alto=320, leyenda=False), width="stretch")
c.ver_tabla(ev.assign(mes=ev["mes"].dt.strftime("%Y-%m")),
            column_config={"ocupacion": st.column_config.NumberColumn("Ocupación", format="percent"),
                           "adr": st.column_config.NumberColumn("ADR", format="%.0f"),
                           "revpar": st.column_config.NumberColumn("RevPAR", format="%.0f")})

# -- 3b. Anticipación de las reservas --------------------------------------------------------------------------
st.subheader("Con cuánta anticipación reservan")
# Una fila por reserva: anticipación = primera noche − fecha en que se creó la reserva
ant = c.leer("""SELECT p.nome_anuncio AS propiedad, n.id_reserva, MIN(n.fecha) AS llegada,
                       MIN(CAST(n.fecha_reserva AS DATE)) AS fecha_reserva, COUNT(*) AS noches
                FROM public.vw_fct_noches n
                JOIN public.dim_propiedades p ON p.id_interno = n.id_propriedade
                WHERE n.vendida
                GROUP BY 1, 2""")
ant["llegada"] = pd.to_datetime(ant["llegada"])
ant["fecha_reserva"] = pd.to_datetime(ant["fecha_reserva"])
ant = ant[ant["propiedad"].isin(anuncios) & (ant["fecha_reserva"] >= CONFIABLE_DESDE)]
solo_periodo = st.toggle("Solo llegadas del período elegido", value=False,
                         help="Apagado: todas las reservas creadas desde "
                              f"{pd.Timestamp(CONFIABLE_DESDE):%d-%m-%Y} (más reservas, patrón más estable).")
if solo_periodo:
    ant = ant[ant["llegada"].dt.to_period("M").dt.to_timestamp().between(desde, hasta)]
if ant.empty:
    st.info("No hay reservas con fecha de creación confiable para este filtro.")
else:
    ant["dias"] = (ant["llegada"] - ant["fecha_reserva"]).dt.days.clip(lower=0)
    tramos = [(2, "0–2 días"), (7, "3–7 días"), (14, "8–14 días"), (30, "15–30 días"), (60, "31–60 días"),
              (10_000, "Más de 60 días")]
    nombres = [t for _, t in tramos]
    ant["tramo"] = pd.cut(ant["dias"], bins=[-1] + [b for b, _ in tramos], labels=nombres)

    k1, k2, k3 = st.columns(3)
    k1.metric("Anticipación mediana", f"{ant['dias'].median():.0f} días",
              help="La mitad de las reservas se hace con menos días que esto.")
    k2.metric("Reservas de último minuto (≤ 7 días)", c.pct((ant["dias"] <= 7).mean()))
    k3.metric("Reservas analizadas", f"{len(ant)}")

    res = (ant.groupby("propiedad").agg(reservas=("id_reserva", "count"), mediana=("dias", "median"),
                                        promedio=("dias", "mean"), p75=("dias", lambda s: s.quantile(0.75)),
                                        noches=("noches", "mean"))
              .reset_index().sort_values(["mediana", "promedio"]))
    res["etiqueta"] = res.apply(lambda r: f"{r.propiedad} · {r.mediana:.0f} d", axis=1)
    reparto = (ant.groupby(["propiedad", "tramo"], observed=False).size().rename("n").reset_index()
                  .merge(res[["propiedad", "etiqueta", "reservas"]], on="propiedad"))
    reparto["part"] = reparto["n"] / reparto["reservas"]

    # 100 % apilado por anuncio: claro = último minuto, oscuro = con mucha anticipación
    colores_t = c.SECUENCIAL[1:]
    fig = go.Figure()
    for tramo, color in zip(nombres, colores_t):
        g = reparto[reparto["tramo"] == tramo].set_index("etiqueta").reindex(res["etiqueta"])
        fig.add_bar(y=g.index, x=g["part"], name=tramo, orientation="h", marker_color=color,
                    customdata=g[["n", "reservas"]],
                    text=g["part"].map(lambda v: c.pct(v) if v >= 0.08 else ""), textposition="inside",
                    insidetextanchor="middle", textfont=dict(color="white" if color in c.SECUENCIAL[3:] else "#1d1d1b"),
                    hovertemplate=f"%{{y}}<br>{tramo}: %{{customdata[0]}} de %{{customdata[1]}} reservas "
                                  "(%{x:.0%})<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.3)
    fig.update_xaxes(tickformat=".0%", range=[0, 1])
    fig.update_yaxes(categoryorder="array", categoryarray=list(res["etiqueta"]), autorange="reversed")
    st.plotly_chart(c.estilo_figura(fig, alto=110 + 34 * len(res)).update_layout(hovermode="closest",
                                                                                legend_traceorder="normal"),
                    width="stretch")
    st.caption("Cada barra reparte las reservas del anuncio según cuántos días antes de la llegada se hicieron. "
               "Junto al nombre, la anticipación **mediana** (d = días); arriba los que se reservan más a última hora. "
               f"Solo reservas creadas desde el {pd.Timestamp(CONFIABLE_DESDE):%d-%m-%Y}: las anteriores se migraron "
               "a Stays y aparecen todas creadas el 15-05-2026. Excluye canceladas.")
    c.ver_tabla(res[["propiedad", "reservas", "mediana", "promedio", "p75", "noches"]],
                column_config={"propiedad": "Anuncio", "reservas": "Reservas",
                               "mediana": st.column_config.NumberColumn("Mediana (días)", format="%.0f"),
                               "promedio": st.column_config.NumberColumn("Promedio (días)", format="%.1f"),
                               "p75": st.column_config.NumberColumn("75 % reserva con menos de (días)", format="%.0f"),
                               "noches": st.column_config.NumberColumn("Noches por reserva", format="%.1f")})

# -- 3c. Reservas y reviews --------------------------------------------------------------------------------
st.subheader("Reservas y reviews")
if c.requiere("analitica.vw_reservas_reviews", "Ejecuta de nuevo `sql/esquema_analitica.sql` y luego "
                                                "`python -m analitica.subir_bigquery` en tu computador."):
    rr, rev_desde = c.reservas_reviews()
    rr = rr[rr["propiedad"].isin(anuncios) & rr["mes_salida"].between(desde, hasta)]
    if rr.empty:
        st.info("No hay reservas con salida en el período (las reviews se cargan desde "
                f"{c.nombre_mes(rev_desde) if rev_desde is not None else '—'}).")
    else:
        tot = c.resumen_reviews(rr, []).iloc[0]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Reservas", f"{int(tot['reservas'])}", help="Reservas no canceladas con salida (check-out) en el período.")
        k2.metric("Estadías terminadas", f"{int(tot['terminadas'])}")
        k3.metric("Dejaron review", f"{int(tot['con_review'])} · {c.pct(tot['tasa'])}",
                  help="Porcentaje sobre las estadías terminadas.")
        k4.metric("Aún pueden dejarla", f"{int(tot['pendientes'])}",
                  help=f"Terminadas hace {c.DIAS_PARA_REVIEW} días o menos y todavía sin review.")

        pm = c.resumen_reviews(rr, ["mes_salida"]).sort_values("mes_salida")
        fig = go.Figure()
        fig.add_bar(x=pm["mes_salida"], y=pm["reservas"], name="Reservas", marker_color=c.AZUL_CLARO,
                    hovertemplate="%{x|%b %Y}: %{y} reservas<extra></extra>")
        fig.add_bar(x=pm["mes_salida"], y=pm["con_review"], name="Con review", marker_color=c.AZUL,
                    text=pm["tasa"].map(c.pct), textposition="outside", cliponaxis=False,
                    customdata=pm[["terminadas"]],
                    hovertemplate="%{x|%b %Y}: %{y} con review de %{customdata[0]} terminadas (%{text})<extra></extra>")
        fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
        fig.update_xaxes(dtick="M1", tickformat="%b %Y")
        fig.update_yaxes(range=[0, pm["reservas"].max() * 1.18])
        st.plotly_chart(c.estilo_figura(fig, alto=300).update_layout(hovermode="x unified"), width="stretch")

        pp = c.resumen_reviews(rr, ["propiedad"]).sort_values(["tasa", "terminadas"], ascending=[False, False])
        fig = go.Figure(go.Bar(
            y=pp["propiedad"], x=pp["tasa"], orientation="h", marker_color=c.AZUL,
            text=[f"{c.pct(t)} · {int(r)} de {int(n)}" for t, r, n in zip(pp["tasa"], pp["con_review"], pp["terminadas"])],
            textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: %{text}<extra></extra>"))
        fig.update_xaxes(tickformat=".0%", range=[0, 1.25])
        fig.update_yaxes(autorange="reversed")
        st.markdown("**% de estadías terminadas que dejaron review, por anuncio**")
        st.plotly_chart(c.estilo_figura(fig, alto=80 + 30 * len(pp), leyenda=False).update_layout(hovermode="closest"),
                        width="stretch")
        st.caption("Por mes de **salida** (check-out): la review llega después de la estadía y Airbnb da "
                   f"{c.DIAS_PARA_REVIEW} días para dejarla, así que los meses recientes todavía pueden subir. "
                   "El % se calcula sobre las estadías ya terminadas; excluye canceladas. "
                   f"Las reviews están cargadas desde {c.nombre_mes(rev_desde)}: los meses anteriores no se cuentan.")
        c.ver_tabla(pd.concat([pm.assign(mes_salida=pm["mes_salida"].map(c.nombre_mes)).rename(columns={"mes_salida": "grupo"}),
                               pp.rename(columns={"propiedad": "grupo"})]),
                    column_config={"grupo": "Mes / anuncio", "reservas": "Reservas", "terminadas": "Terminadas",
                                   "con_review": "Con review", "pendientes": "Aún pueden dejarla",
                                   "tasa": st.column_config.NumberColumn("% con review", format="percent"),
                                   "nota": st.column_config.NumberColumn("Nota promedio", format="%.2f")})

# -- 4. Pronóstico ---------------------------------------------------------------------------------------
st.divider()
st.subheader("Pronóstico")
if not c.requiere("analitica.vw_pronostico_actual",
                  "Corre `python -m analitica.pronostico --guardar` y luego `python -m analitica.subir_bigquery`."):
    st.stop()
pr = c.leer("""SELECT propiedad, fecha_corte, mes, moneda, disponibles, reservadas_ya, noches_pronostico,
                      ocupacion_ya, ocupacion_pronostico, ingreso_ya, ingreso_pronostico
               FROM analitica.vw_pronostico_actual ORDER BY mes""")
pr = pr[pr["propiedad"].isin(anuncios)]
if pr.empty:
    st.info("No hay pronóstico guardado para estos anuncios. Corre `python -m analitica.pronostico --guardar` "
            "y luego `python -m analitica.subir_bigquery`.")
    st.stop()
st.caption(f"Calculado el {pd.Timestamp(pr['fecha_corte'].iloc[0]):%d-%m-%Y}. Método pickup: "
           "lo ya reservado + noches libres × probabilidad histórica de venderse con esa anticipación. "
           "Aún no considera temporada. (No depende del filtro de meses.)")
mes_p = st.selectbox("Mes del pronóstico", sorted(pr["mes"].unique()), format_func=c.nombre_mes)
g = pr[pr["mes"] == mes_p].copy().sort_values("ocupacion_pronostico")

d1, d2 = st.columns([1, 2], gap="large")
with d1:
    tot = g["disponibles"].sum()
    ya, pron = g["reservadas_ya"].sum() / tot, g["noches_pronostico"].sum() / tot
    fig = go.Figure(go.Pie(labels=[f"Ya reservado {c.pct(ya)}", f"Se espera vender {c.pct(pron - ya)}",
                                   f"Quedaría libre {c.pct(1 - pron)}"],
                           values=[ya, pron - ya, 1 - pron], hole=0.62, sort=False,
                           marker=dict(colors=[c.AZUL, c.AZUL_CLARO, c.PISTA], line=dict(color="white", width=2)),
                           textinfo="none", hovertemplate="%{label}<extra></extra>"))
    fig.add_annotation(text=f"<b>{c.pct(pron)}</b><br>pronóstico", showarrow=False, font=dict(size=16))
    fig.update_layout(height=320, margin=dict(l=8, r=8, t=8, b=8),
                      legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center"))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
with d2:
    g["adicional"] = g["ocupacion_pronostico"] - g["ocupacion_ya"]
    fig = go.Figure()
    fig.add_bar(y=g["propiedad"], x=g["ocupacion_ya"], orientation="h", name="Ya reservado", marker_color=c.AZUL,
                hovertemplate="Ya reservado: %{x:.0%}<extra></extra>")
    fig.add_bar(y=g["propiedad"], x=g["adicional"], orientation="h", name="Se espera vender", marker_color=c.AZUL_CLARO,
                hovertemplate="Se espera vender: %{x:.0%}<extra></extra>",
                text=g["ocupacion_pronostico"].map(lambda x: c.pct(x)), textposition="outside", cliponaxis=False)
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_traces(marker_line_width=0)
    fig.update_xaxes(tickformat=".0%", range=[0, 1.12])
    st.plotly_chart(c.estilo_figura(fig, alto=max(320, 80 + 34 * len(g)))
                    .update_layout(hovermode="y unified", legend_traceorder="normal"), width="stretch")
c.ver_tabla(g[["propiedad", "moneda", "disponibles", "reservadas_ya", "noches_pronostico", "ocupacion_ya",
               "ocupacion_pronostico", "ingreso_ya", "ingreso_pronostico"]].sort_values("ocupacion_pronostico", ascending=False),
            column_config={"ocupacion_ya": st.column_config.NumberColumn("Ya reservado", format="percent"),
                           "ocupacion_pronostico": st.column_config.NumberColumn("Pronóstico", format="percent"),
                           "noches_pronostico": st.column_config.NumberColumn("Noches pronosticadas", format="%.1f"),
                           "ingreso_ya": st.column_config.NumberColumn("Ingreso ya reservado", format="%.0f"),
                           "ingreso_pronostico": st.column_config.NumberColumn("Ingreso pronosticado", format="%.0f")})

# -- 5. Noches libres próximas ------------------------------------------------------------------------------
st.subheader("Noches libres en los próximos 21 días")
st.caption("Cada celda es una noche: gris = ya reservada; azul = libre, más oscuro = más probable que se venda "
           "a tiempo. Las celdas claras son las que necesitan precio o promoción.")
pn = c.leer("""SELECT p.nome_anuncio AS propiedad, pn.fecha, pn.reservada, pn.probabilidad
               FROM analitica.pronostico_noches pn
               JOIN public.dim_propiedades p ON p.id_interno = pn.id_propriedade
               WHERE pn.fecha_corte = (SELECT MAX(fecha_corte) FROM analitica.pronostico_noches)
                 AND pn.fecha < DATE_ADD((SELECT MAX(fecha_corte) FROM analitica.pronostico_noches), INTERVAL 21 DAY)""")
pn = pn[pn["propiedad"].isin(anuncios)]
if not pn.empty:
    pn["fecha"] = pd.to_datetime(pn["fecha"])
    pn["valor"] = pn["probabilidad"].where(~pn["reservada"])
    piv = pn.pivot_table(index="propiedad", columns="fecha", values="valor", aggfunc="first", dropna=False)
    res = pn.pivot_table(index="propiedad", columns="fecha", values="reservada", aggfunc="first")
    orden = piv.isna().sum(axis=1).sort_values().index  # más noches libres arriba
    piv, res = piv.loc[orden], res.loc[orden]
    etiquetas = [f"{c.DIAS[d.weekday()]} {d:%d}" for d in piv.columns]
    fig = go.Figure()
    fig.add_heatmap(z=res.astype(float).where(res).values, x=etiquetas, y=list(piv.index),
                    colorscale=[[0, c.GRIS], [1, c.GRIS]], showscale=False, hoverinfo="skip", xgap=2, ygap=2)
    fig.add_heatmap(z=piv.values, x=etiquetas, y=list(piv.index), zmin=0, zmax=1, xgap=2, ygap=2,
                    colorscale=[[i / (len(c.SECUENCIAL) - 1), col] for i, col in enumerate(c.SECUENCIAL)],
                    colorbar=dict(title="Prob.", tickformat=".0%", thickness=10),
                    hovertemplate="%{y} · %{x}<br>Probabilidad de venderse: %{z:.0%}<extra></extra>")
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(c.estilo_figura(fig, alto=80 + 30 * len(piv), leyenda=False).update_layout(hovermode="closest"),
                    width="stretch")
    libres = pn[~pn["reservada"]].assign(Fecha=lambda d: d["fecha"].map(lambda x: f"{c.DIAS[x.weekday()]} {x:%d-%m}"))
    c.ver_tabla(libres.sort_values(["probabilidad"])[["propiedad", "Fecha", "probabilidad"]],
                "Ver noches libres (de menor a mayor probabilidad)",
                column_config={"probabilidad": st.column_config.NumberColumn("Prob. de venderse", format="percent")})
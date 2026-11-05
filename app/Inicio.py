"""Portada del dashboard:  streamlit run app/Inicio.py"""
import pandas as pd
import streamlit as st
#corre con comando:
#                   streamlit run app/Inicio.py
import comun as c
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] if Path(__file__).parent.name == "app" else Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
c.configurar("Andina · Resumen")
if not c.conexion_ok():
    st.stop()

hoy = pd.Timestamp(c.hoy())
hoy_mes = hoy.replace(day=1)
mes_cerrado = hoy_mes - pd.DateOffset(months=1)
meta = c.META_INGRESO_MENSUAL_CLP


def variacion(actual, anterior):
    """Cambio porcentual, o None si falta alguno de los dos (mes sin ventas, por ejemplo)."""
    if pd.isna(actual) or pd.isna(anterior) or not anterior:
        return None
    return f"{actual / anterior - 1:+.1%}".replace(".", ",")


def tarjetas_mercado(m, ant, mes_ant):
    """Ocupación, ADR y RevPAR de las noches ya ocurridas de un mercado, comparados con `ant` (mes anterior)."""
    vs = f" vs. {c.nombre_mes(mes_ant)}"
    mon = m["moneda_local"]
    d_ocup = None if ant is None or pd.isna(m["ocupacion_fecha"]) or pd.isna(ant["ocupacion_fecha"]) else \
        f"{(m['ocupacion_fecha'] - ant['ocupacion_fecha']) * 100:+.1f} pp".replace(".", ",") + vs
    d_adr, d_revpar = (None, None) if ant is None else (variacion(m["adr_fecha"], ant["adr_fecha"]),
                                                        variacion(m["revpar_fecha"], ant["revpar_fecha"]))
    columnas = st.columns(4)
    columnas[0].metric("Ocupación", c.pct(m["ocupacion_fecha"]), d_ocup,
                       help="Noches vendidas sobre las noches que ya ocurrieron en el mes.")
    columnas[1].metric(f"ADR ({mon})", c.dinero(m["adr_fecha"]), d_adr and d_adr + vs,
                       help="Precio promedio por noche vendida.")
    columnas[2].metric(f"RevPAR ({mon})", c.dinero(m["revpar_fecha"]), d_revpar and d_revpar + vs,
                       help="Ingreso por noche disponible, vendida o no.")
    return columnas[3]


kp = None
if c.requiere("public.vw_fct_noches", c.COMO_ACTUALIZAR):
    kp = c.mes_completo()

# -- Lo que llevamos del mes en curso ---------------------------------------------------------------------
if kp is not None:
    actual = kp[kp["mes"] == hoy_mes]
    total, futuro = float(actual["ingreso_alojamiento_clp"].sum()), float(actual["ingreso_futuro_clp"].sum())
    cumpl = total / meta
    _, estado = c.estado_meta(cumpl)
    dias_mes = hoy.days_in_month
    st.subheader(f"Lo que llevamos de {c.nombre_mes(hoy_mes)}")
    st.caption(f"Día **{hoy.day} de {dias_mes}**. Meta: **{c.dinero(meta, 'CLP')} al mes** "
               "(todo el portafolio, Brasil convertido a CLP).")
    k1, k2, k3 = st.columns(3)
    k1.metric("Ingreso del mes, reservado a hoy", c.dinero(total, "CLP"), f"{c.pct(cumpl)} de la meta · {estado}",
              delta_color="normal" if cumpl >= 1 else "inverse",
              help="Noches ya ocurridas más noches futuras de este mes ya reservadas. Es el mismo número de "
                   "Finanzas; puede subir con nuevas reservas o bajar con cancelaciones.")
    k2.metric("Ya ocurrido", c.dinero(total - futuro, "CLP"), help="Ingreso de las noches anteriores a hoy.")
    k3.metric("Reservado por ocurrir", c.dinero(futuro, "CLP"),
              help="Ingreso de las noches desde hoy hasta fin de mes que ya están reservadas.")
    st.progress(min(max(cumpl, 0.0), 1.0),
                text="Meta cumplida" if cumpl >= 1 else f"Faltan {c.dinero(meta - total, 'CLP')} para la meta")

    res_actual = c.resumen_mes(kp, hoy_mes)
    res_cerrado = c.resumen_mes(kp, mes_cerrado).set_index("mercado")
    for _, m in res_actual.iterrows():
        st.markdown(f"**{m['mercado']}** · noches ya ocurridas")
        ant = res_cerrado.loc[m["mercado"]] if m["mercado"] in res_cerrado.index else None
        tarjetas_mercado(m, ant, mes_cerrado).metric(
            f"Reservado: {int(m['vendidas'])} de {int(m['disponibles'])} noches", c.pct(m["ocupacion_mes"]),
            help="Noches ya ocurridas más futuras ya reservadas, sobre todas las noches del mes. "
                 "Es la ocupación que muestra la página Ocupación.")
    if res_actual.empty:
        st.info("Aún no hay noches cargadas para este mes.")

# -- Cómo nos fue con las reviews -------------------------------------------------------------------------
if c.existe("public.vw_reviews_mensual") and c.existe("public.vw_reviews_actual"):
    rm = c.leer("""SELECT propiedad, CAST(mes AS DATE) AS mes, reviews_con_nota, suma_general, general,
                          reviews_bajo_5, nota_minima
                   FROM public.vw_reviews_mensual WHERE reviews_con_nota > 0""")
    rm["mes"] = pd.to_datetime(rm["mes"])
    if not rm.empty:
        st.divider()
        st.subheader("Cómo nos fue con las reviews")
        meses_rv = sorted((pd.Timestamp(m) for m in rm["mes"].unique()), reverse=True)
        mes_rv = st.selectbox("Mes en que llegó la review", meses_rv,
                              format_func=lambda m: c.nombre_mes(m) + (" (en curso)" if m == hoy_mes else ""))
        ev = c.evaluar_reviews(rm[rm["mes"] == mes_rv])
        mes_antes = mes_rv - pd.DateOffset(months=1)
        ev_antes = c.evaluar_reviews(rm[rm["mes"] == mes_antes])
        coma = lambda v: f"{v:.2f}".replace(".", ",")  # noqa: E731
        st.markdown(f"**{ev['veredicto']}**" + (" hasta ahora: el mes sigue sumando reviews." if mes_rv == hoy_mes else "."))

        actual_rv = c.leer("""SELECT propiedad, criticidad, promedio_acumulado, promedio_3m,
                                     peor_categoria_3m, peor_nota_3m FROM public.vw_reviews_actual""")
        por_estado = actual_rv["criticidad"].value_counts()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Nota del mes", coma(ev["nota"]),
                  None if ev_antes["nota"] is None else
                  f"{ev['nota'] - ev_antes['nota']:+.2f}".replace(".", ",") + f" vs. {c.nombre_mes(mes_antes)}",
                  help="Promedio de todas las reviews recibidas en el mes, de todos los anuncios.")
        k2.metric("Reviews recibidas", f"{ev['reviews']}",
                  help=f"En {c.nombre_mes(mes_antes)} fueron {ev_antes['reviews']}.")
        k3.metric(f"Con 5 estrellas (la más baja: {ev['minima']:.0f})", f"{ev['cinco']} de {ev['reviews']}")
        k4.metric(f"Anuncios en OK ({por_estado.get('Alerta', 0)} 🟠 · {por_estado.get('Crítico', 0)} 🔴)",
                  f"{por_estado.get('OK', 0)} de {len(actual_rv)}",
                  help="Estado actual de cada anuncio, con sus reglas de Reviews. No cambia con el selector de mes.")

        mes_tabla = rm[rm["mes"] == mes_rv].set_index("propiedad")
        tabla = actual_rv.assign(
            orden=actual_rv["criticidad"].map({"Crítico": 0, "Alerta": 1, "OK": 2}).fillna(3),
            Estado=actual_rv["criticidad"].map(c.ESTADO).fillna(actual_rv["criticidad"]),
            reviews_mes=actual_rv["propiedad"].map(mes_tabla["reviews_con_nota"]).fillna(0).astype(int),
            nota_mes=actual_rv["propiedad"].map(mes_tabla["general"]),
            bajo_5=actual_rv["propiedad"].map(mes_tabla["reviews_bajo_5"]).fillna(0).astype(int),
        ).sort_values(["orden", "promedio_acumulado"])
        st.dataframe(tabla[["propiedad", "Estado", "reviews_mes", "nota_mes", "bajo_5", "promedio_3m",
                            "promedio_acumulado", "peor_categoria_3m", "peor_nota_3m"]],
                     hide_index=True, width="stretch", height=38 + 35 * len(tabla),
                     column_config={"propiedad": st.column_config.TextColumn("Anuncio", width="medium"),
                                    "Estado": "Estado hoy", "reviews_mes": "Reviews del mes",
                                    "nota_mes": st.column_config.NumberColumn("Nota del mes", format="%.2f"),
                                    "bajo_5": "Bajo 5",
                                    "promedio_3m": st.column_config.NumberColumn("3 meses", format="%.2f"),
                                    "promedio_acumulado": st.column_config.NumberColumn("Acumulado", format="%.2f"),
                                    "peor_categoria_3m": "Categoría más baja 3m",
                                    "peor_nota_3m": st.column_config.NumberColumn("Su nota", format="%.2f")})
        st.caption("🟢 Buen mes: nota de 4,90 o más · 🟠 Regular: desde 4,80 · 🔴 Con problemas: bajo 4,80 o alguna "
                   f"review de 3 o menos · ⚪ menos de {c.MIN_REVIEWS_EVALUAR} reviews. Se cuenta por fecha de la review. "
                   "El detalle y los comentarios están en **Reviews**.")

# -- Reservas y reviews del mes ------------------------------------------------------------------------
if c.existe("analitica.vw_reservas_reviews"):
    rr, rev_desde = c.reservas_reviews()
    if not rr.empty:
        st.divider()
        st.subheader("Reservas y reviews")
        meses_rr = sorted((pd.Timestamp(m) for m in rr["mes_salida"].unique()), reverse=True)
        mes_rr = st.selectbox("Mes analizado (por fecha de salida)", meses_rr,
                              index=meses_rr.index(hoy_mes) if hoy_mes in meses_rr else 0,
                              format_func=lambda m: c.nombre_mes(m) + (" (en curso)" if m == hoy_mes else ""))
        tot = c.resumen_reviews(rr[rr["mes_salida"] == mes_rr], []).iloc[0]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Reservas", f"{int(tot['reservas'])}", help="Reservas no canceladas con salida en el mes.")
        k2.metric("Estadías terminadas", f"{int(tot['terminadas'])}")
        k3.metric("Dejaron review", f"{int(tot['con_review'])} · {c.pct(tot['tasa'])}",
                  help="Porcentaje sobre las estadías terminadas.")
        k4.metric("Aún pueden dejarla", f"{int(tot['pendientes'])}",
                  help=f"Terminadas hace {c.DIAS_PARA_REVIEW} días o menos y todavía sin review.")
        st.caption(f"Airbnb da {c.DIAS_PARA_REVIEW} días después del check-out para dejar la review. Qué departamentos "
                   "tienen review y cuáles no está en **Reviews**; la evolución por mes, en **Ocupación**.")

st.divider()
col2, col3 = st.columns(2, gap="large")

# -- Pronóstico -----------------------------------------------------------------------------------
with col2:
    st.subheader("Pronóstico")
    if c.existe("analitica.vw_pronostico_actual"):
        pr = c.leer("""SELECT fecha_corte, mes, moneda, disponibles, reservadas_ya, noches_pronostico
                     FROM analitica.vw_pronostico_actual""")
        if pr.empty:
            st.info("Corre `python -m analitica.pronostico --guardar` y luego `python -m analitica.subir_bigquery`.")
        else:
            fc = pd.Timestamp(pr["fecha_corte"].iloc[0])
            pr = pr[pd.to_datetime(pr["mes"]) >= hoy_mes]      # un pronóstico antiguo puede traer meses ya cerrados
            for (mes, mon), g in c.chile_primero(pr, ["mes", "moneda"]).groupby(["mes", "moneda"], sort=False):
                st.markdown(f"**{c.nombre_mes(mes)}** ({mon}): {c.pct(g['noches_pronostico'].sum() / g['disponibles'].sum())} "
                            f"pronosticado · {c.pct(g['reservadas_ya'].sum() / g['disponibles'].sum())} "
                            f"reservado al {fc:%d-%m}")
            dias = (hoy - fc).days
            st.caption(f"Calculado el {fc:%d-%m-%Y}" + (" — conviene actualizarlo." if dias > 7 else "."))

# -- Noches libres -------------------------------------------------------------------------------
with col3:
    st.subheader("Próximos 7 días")
    if kp is not None:
        # Desde las reservas y no desde el pronóstico guardado, que puede tener semanas
        rz = c.leer("""
            WITH propiedades AS (
                SELECT n.id_propriedade, MIN(n.fecha) AS alta, pf.fecha_baja
                FROM public.vw_fct_noches n
                LEFT JOIN public.propiedad_fechas pf ON pf.id_propriedade = n.id_propriedade
                GROUP BY n.id_propriedade, pf.fecha_baja
            ),
            vendidas AS (SELECT DISTINCT id_propriedade, fecha FROM public.vw_fct_noches WHERE vendida)
            SELECT pr.nome_anuncio AS propiedad, COUNT(*) AS libres
            FROM propiedades p
            CROSS JOIN UNNEST(GENERATE_DATE_ARRAY(@hoy, DATE_ADD(@hoy, INTERVAL 6 DAY))) AS fecha
            JOIN public.dim_propiedades pr ON pr.id_interno = p.id_propriedade
            LEFT JOIN vendidas v ON v.id_propriedade = p.id_propriedade AND v.fecha = fecha
            WHERE v.fecha IS NULL AND fecha >= p.alta AND (p.fecha_baja IS NULL OR fecha < p.fecha_baja)
            GROUP BY propiedad ORDER BY libres DESC""", {"hoy": c.hoy()})
        if rz.empty:
            st.markdown("Sin noches libres. 🎉")
        else:
            st.markdown(f"**{int(rz['libres'].sum())} noches libres** en {len(rz)} propiedades.")
            st.dataframe(rz.rename(columns={"propiedad": "Propiedad", "libres": "Noches libres"}),
                         hide_index=True, width="stretch")

# -- Último mes cerrado (referencia: lo del mes en curso va arriba) -------------------------------------
if kp is not None and (kp["mes"] == mes_cerrado).any():
    st.divider()
    with st.expander(f"Último mes cerrado: {c.nombre_mes(mes_cerrado)}"):
        ingreso = float(kp.loc[kp["mes"] == mes_cerrado, "ingreso_alojamiento_clp"].sum())
        _, estado = c.estado_meta(ingreso / meta)
        st.metric("Ingreso del mes", c.dinero(ingreso, "CLP"), f"{c.pct(ingreso / meta)} de la meta · {estado}",
                  delta_color="normal" if ingreso >= meta else "inverse")
        mes_previo = mes_cerrado - pd.DateOffset(months=1)
        res_previo = c.resumen_mes(kp, mes_previo).set_index("mercado")
        for _, m in c.resumen_mes(kp, mes_cerrado).iterrows():
            st.markdown(f"**{m['mercado']}**")
            ant = res_previo.loc[m["mercado"]] if m["mercado"] in res_previo.index else None
            tarjetas_mercado(m, ant, mes_previo).metric(
                "Noches vendidas", f"{int(m['vendidas'])} de {int(m['disponibles'])}")

# -- Controles de datos --------------------------------------------------------------------------
if c.existe("public.vw_controles_calidad"):
    ctl = c.leer("SELECT control, resultado FROM public.vw_controles_calidad WHERE estado <> 'OK' ORDER BY prioridad, n")
    if not ctl.empty:
        st.divider()
        st.warning(f"{len(ctl)} controles de calidad de datos para revisar en andina_lab.")
        c.ver_tabla(ctl.rename(columns={"control": "Control", "resultado": "Resultado"}), "Ver controles")

st.divider()
st.caption("Para actualizar: importa en andina_lab → `python -m analitica.pronostico --guardar` → "
           "`python -m analitica.reviews_ia` → `python -m analitica.subir_bigquery`. El dashboard lo detecta solo "
           "en máx. 10 minutos; para verlo al tiro, usa 🔄 Actualizar datos en la barra lateral.")

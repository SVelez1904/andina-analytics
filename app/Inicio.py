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

# -- KPI financiero: ingresos vs meta -----------------------------------------------------------
if c.existe("public.vw_fct_noches"):
    ing = c.leer("""SELECT DATE_TRUNC(fecha, MONTH) AS mes, COALESCE(SUM(ingreso_noche_clp), 0) AS ingreso_clp
                    FROM public.vw_fct_noches
                    WHERE vendida
                      AND fecha >= DATE_SUB(DATE_TRUNC(CURRENT_DATE('America/Santiago'), MONTH), INTERVAL 1 MONTH)
                      AND fecha <= LAST_DAY(CURRENT_DATE('America/Santiago'), MONTH)
                    GROUP BY 1 ORDER BY 1""")
    meta = c.META_INGRESO_MENSUAL_CLP
    st.subheader("Ingresos vs meta")
    st.caption(f"Meta: **{c.dinero(meta, 'CLP')} al mes** (todo el portafolio, Brasil convertido a CLP).")
    hoy_mes = pd.Timestamp.today().normalize().replace(day=1)
    ing["mes"] = pd.to_datetime(ing["mes"])
    for col_, (etiqueta, fila) in zip(st.columns(2), [
            ("último mes cerrado", ing[ing["mes"] < hoy_mes]),
            ("en curso, reservado a la fecha", ing[ing["mes"] >= hoy_mes])]):
        mes = c.nombre_mes(hoy_mes - pd.DateOffset(months=1) if "cerrado" in etiqueta else hoy_mes)
        valor = float(fila["ingreso_clp"].sum())
        cumpl = valor / meta
        _, estado = c.estado_meta(cumpl)
        col_.metric(f"{mes} ({etiqueta})", c.dinero(valor, "CLP"),
                    f"{c.pct(cumpl)} de la meta · {estado}", delta_color="normal" if cumpl >= 1 else "inverse")
        col_.progress(min(cumpl, 1.0), text=("Meta cumplida" if cumpl >= 1
                                             else f"Faltan {c.dinero(meta - valor, 'CLP')}"))
    st.divider()

# -- Último mes cerrado por mercado --------------------------------------------------------
if c.requiere("public.vw_kpis_mercado_mensual", c.COMO_ACTUALIZAR):
    km = c.leer("SELECT * FROM public.vw_kpis_mercado_mensual WHERE mes_cerrado ORDER BY mercado, mes")
    km = c.chile_primero(km, ["mercado", "mes"])
    if km.empty:
        st.info("Aún no hay meses cerrados con datos.")
    for mercado, g in km.groupby("mercado", sort=False):
        g = g.sort_values("mes")
        ult = g.iloc[-1]
        ant = g.iloc[-2] if len(g) > 1 else None
        mon = ult["moneda_local"]
        st.subheader(f"{mercado} · {c.nombre_mes(ult['mes'])}")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Ocupación", c.pct(ult["ocupacion"]),
                  None if ant is None else f"{(ult['ocupacion'] - ant['ocupacion']) * 100:+.1f} pp vs. mes anterior")
        k2.metric(f"ADR ({mon})", c.dinero(ult["adr"]),
                  None if ant is None or not ant["adr"] else f"{ult['adr'] / ant['adr'] - 1:+.1%}")
        k3.metric(f"RevPAR ({mon})", c.dinero(ult["revpar"]),
                  None if ant is None or not ant["revpar"] else f"{ult['revpar'] / ant['revpar'] - 1:+.1%}")
        k4.metric("Noches vendidas", f"{int(ult['noches_vendidas'])} de {int(ult['noches_disponibles'])}")

st.divider()
col1, col2, col3 = st.columns(3)

# -- Reviews -----------------------------------------------------------------------------------
with col1:
    st.subheader("Reviews")
    if c.existe("public.vw_reviews_actual"):
        rv = c.leer("SELECT propiedad, criticidad, promedio_acumulado, motivo FROM public.vw_reviews_actual")
        orden = ["Crítico", "Alerta", "OK", "Sin datos suficientes"]
        rv["orden"] = rv["criticidad"].map({k: i for i, k in enumerate(orden)})
        rv = rv.sort_values(["orden", "promedio_acumulado"])
        for estado in ("Crítico", "Alerta"):
            props = rv.loc[rv["criticidad"] == estado, "propiedad"].tolist()
            if props:
                st.markdown(f"**{c.ESTADO[estado]}** ({len(props)}): " + ", ".join(props))
        if not rv["criticidad"].isin(["Crítico", "Alerta"]).any():
            st.markdown("🟢 Todas las propiedades en OK.")
    else:
        st.info(c.COMO_ACTUALIZAR)

# -- Pronóstico -----------------------------------------------------------------------------------
with col2:
    st.subheader("Pronóstico")
    if c.existe("analitica.vw_pronostico_actual"):
        pr = c.leer("SELECT * FROM analitica.vw_pronostico_actual")
        if pr.empty:
            st.info("Corre `python -m analitica.pronostico --guardar` y luego `python -m analitica.subir_bigquery`.")
        else:
            fc = pd.Timestamp(pr["fecha_corte"].iloc[0])
            for (mes, mon), g in c.chile_primero(pr, ["mes", "moneda"]).groupby(["mes", "moneda"], sort=False):
                st.markdown(f"**{c.nombre_mes(mes)}** ({mon}): {c.pct(g['noches_pronostico'].sum() / g['disponibles'].sum())} "
                            f"pronosticado · {c.pct(g['reservadas_ya'].sum() / g['disponibles'].sum())} ya reservado")
            dias = (pd.Timestamp.today().normalize() - fc).days
            st.caption(f"Calculado el {fc:%d-%m-%Y}" + (" — conviene actualizarlo." if dias > 7 else "."))

# -- Noches libres -------------------------------------------------------------------------------
with col3:
    st.subheader("Próximos 7 días")
    if c.existe("analitica.vw_noches_en_riesgo"):
        rz = c.leer("""SELECT propiedad, COUNT(*) AS libres FROM analitica.vw_noches_en_riesgo
                       WHERE dias_para_la_noche <= 6 GROUP BY propiedad ORDER BY libres DESC""")
        if rz.empty:
            st.markdown("Sin noches libres (o falta correr el pronóstico).")
        else:
            st.markdown(f"**{int(rz['libres'].sum())} noches libres** en {len(rz)} propiedades.")
            st.dataframe(rz.rename(columns={"propiedad": "Propiedad", "libres": "Noches libres"}),
                         hide_index=True, width="stretch")

# -- Controles de datos --------------------------------------------------------------------------
if c.existe("public.vw_controles_calidad"):
    ctl = c.leer("SELECT control, resultado FROM public.vw_controles_calidad WHERE estado <> 'OK' ORDER BY prioridad, n")
    if not ctl.empty:
        st.divider()
        st.warning(f"{len(ctl)} controles de calidad de datos para revisar en andina_lab.")
        c.ver_tabla(ctl.rename(columns={"control": "Control", "resultado": "Resultado"}), "Ver controles")

st.divider()
st.caption("Para actualizar: importa en andina_lab → `python -m analitica.pronostico --guardar` → "
           "`python -m analitica.reviews_ia` → `python -m analitica.subir_bigquery` → recarga esta página "
           "(los datos se guardan en caché 5 minutos).")

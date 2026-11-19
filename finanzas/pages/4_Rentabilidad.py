from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from lib import bq
from lib.auth import usuario_actual
from lib.config import tabla

st.set_page_config(page_title="Rentabilidad", page_icon="📈", layout="wide")
u = usuario_actual()
st.title("Rentabilidad por propiedad")

anio = st.selectbox("Año", list(range(date.today().year, date.today().year - 5, -1)))
params = [bq.p("anio", "INT64", anio)]
filtro = ""
if u.permitidas() is not None:
    filtro = "AND propiedad_id IN UNNEST(@perm)"
    params.append(bq.pa("perm", "STRING", u.permitidas()))

anual = bq.consultar(f"SELECT * FROM {tabla('pnl_anual')} WHERE anio = @anio {filtro} ORDER BY moneda, resultado DESC", params)
mensual = bq.consultar(f"SELECT * FROM {tabla('pnl_mensual')} WHERE anio = @anio {filtro} ORDER BY mes", params)

if anual.empty:
    st.info("No hay datos confirmados para este año.")
    st.stop()

# NUMERIC de BigQuery llega como Decimal: se convierte a número para tablas y gráficos
anual = anual.map(lambda v: float(v) if isinstance(v, Decimal) else v)
mensual = mensual.map(lambda v: float(v) if isinstance(v, Decimal) else v)

fmt_pct = st.column_config.NumberColumn(format="percent")
for moneda, grupo in anual.groupby("moneda"):
    st.subheader(f"Resumen anual — {moneda}")
    st.dataframe(
        grupo[["propiedad", "modelo_negocio", "ingresos", "comisiones", "gastos_operativos", "mantenimiento",
               "gastos_fijos", "resultado", "margen", "roi_anual", "noches_vendidas", "adr"]],
        column_config={"margen": fmt_pct, "roi_anual": st.column_config.NumberColumn("ROI anual", format="percent"),
                       "ingresos": st.column_config.NumberColumn(format="localized"),
                       "resultado": st.column_config.NumberColumn(format="localized")},
        hide_index=True, use_container_width=True)

st.subheader("Mes a mes")
opciones = mensual["propiedad_id"].unique().tolist()
prop = st.selectbox("Propiedad", opciones,
                    format_func=lambda x: mensual.loc[mensual["propiedad_id"] == x, "propiedad"].iloc[0])
sel = mensual[mensual["propiedad_id"] == prop].copy()
sel["mes"] = pd.to_datetime(sel["mes"]).dt.strftime("%Y-%m")
st.bar_chart(sel.set_index("mes")[["ingresos", "gastos_totales", "resultado"]])
st.dataframe(sel[["mes", "moneda", "ingresos", "comisiones", "gastos_operativos", "mantenimiento", "gastos_fijos",
                  "gastos_totales", "resultado", "margen", "ocupacion", "adr"]],
             column_config={"margen": fmt_pct, "ocupacion": st.column_config.NumberColumn("Ocupación", format="percent")},
             hide_index=True, use_container_width=True)
st.caption("Ingresos por fecha de check-in. Ocupación aproximada: noches de reservas que comienzan en el mes / días del mes.")

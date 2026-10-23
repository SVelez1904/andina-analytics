"""Finanzas: de dónde sale el ingreso del KPI (reserva por reserva) y qué se considera."""
import pandas as pd
import plotly.express as px
import streamlit as st
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] if Path(__file__).parent.name == "app" else Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import comun as c

c.configurar("Finanzas")
if not c.conexion_ok() or not c.requiere("analitica.vw_finanzas_reservas",
                                         "Ejecuta de nuevo `sql/esquema_analitica.sql` y luego "
                                         "`python -m analitica.subir_bigquery` en tu computador."):
    st.stop()

meses = pd.to_datetime(c.leer("SELECT DISTINCT mes FROM analitica.vw_finanzas_reservas WHERE considerada "
                              "ORDER BY mes DESC")["mes"]).tolist()
if not meses:
    st.info("Aún no hay reservas con ingreso.")
    st.stop()
hoy_mes = pd.Timestamp.now(tz="America/Santiago").tz_localize(None).normalize().replace(day=1)
mes = st.selectbox("Mes", meses, index=meses.index(hoy_mes) if hoy_mes in meses else 0,
                   format_func=lambda m: c.nombre_mes(m) + (" (en curso)" if m == hoy_mes else
                                                            " (futuro)" if m > hoy_mes else ""))

df = c.leer("SELECT * FROM analitica.vw_finanzas_reservas WHERE mes = @mes", {"mes": mes.date()})
df = c.chile_primero(df, ["mercado", "propiedad", "llegada"])
fin = df[df["considerada"]].copy()
canceladas = df[~df["considerada"]]

# Montos de la reserva llevados a las noches de este mes (una reserva de 31-ene a 3-feb aporta 1/3 a enero)
fin["fraccion"] = fin["noches_mes"] / fin["noches_reserva"]
for col in ("total_reserva", "limpieza", "comision"):
    fin[f"{col}_mes"] = fin[col].fillna(0) * fin["fraccion"]
fin["tipo_cambio"] = fin["ingreso_mes_clp"] / fin["ingreso_mes_original"].where(fin["ingreso_mes_original"] != 0)

# -- Resultado ----------------------------------------------------------------------------------------
total = float(fin["ingreso_mes_clp"].sum())
meta = c.META_INGRESO_MENSUAL_CLP
noches = int(fin["noches_mes"].sum())
k1, k2, k3, k4 = st.columns(4)
_, estado = c.estado_meta(total / meta)
k1.metric("Ingreso por alojamiento (CLP)", c.dinero(total, "CLP"), f"{c.pct(total / meta)} de la meta · {estado}",
          delta_color="normal" if total >= meta else "inverse",
          help="Es el mismo número de Inicio y del reporte semanal (KPI de ingresos vs meta).")
k2.metric("Reservas consideradas", f"{fin['id_reserva'].nunique()}")
k3.metric("Noches vendidas", f"{noches}")
k4.metric("Promedio por noche (CLP)", c.dinero(total / noches if noches else None))
if mes >= hoy_mes:
    st.caption("Mes en curso o futuro: incluye las noches ya reservadas que todavía no ocurren, "
               "así que puede subir con nuevas reservas o bajar con cancelaciones.")

# -- Cómo se calcula ------------------------------------------------------------------------------------
st.subheader("Cómo se llega al número")
st.markdown(
    "Por cada reserva **no cancelada**:\n\n"
    "1. **Ingreso por alojamiento** = total de la reserva − tarifa de limpieza.\n"
    "2. Se reparte **en partes iguales por noche** (÷ noches de la reserva) y se suman solo las noches que caen "
    "en este mes. Una reserva que cruza de un mes a otro aporta a ambos.\n"
    "3. Se convierte a **CLP** con el tipo de cambio del mes de cada noche (`tipo_cambio_mensual` de andina_lab; "
    "si falta el mes, el valor fijo de `tipo_cambio`).\n"
    "4. Se suman todas las reservas de todas las propiedades, Chile y Brasil.\n\n"
    "**No se descuentan** la comisión de la plataforma ni costos de operación: es ingreso bruto por alojamiento. "
    "**No suman** las reservas canceladas ni las noches anteriores a la fecha de alta (o posteriores a la baja) "
    "de cada propiedad.")

puente = []
for (mercado, moneda), g in fin.groupby(["mercado", "moneda"], sort=False):
    original = g["ingreso_mes_original"].sum()
    clp = g["ingreso_mes_clp"].sum()
    puente.append({
        "Mercado": f"{mercado} ({moneda})", "Reservas": g["id_reserva"].nunique(), "Noches": int(g["noches_mes"].sum()),
        "Total reservas": g["total_reserva_mes"].sum(), "− Limpieza": -g["limpieza_mes"].sum(),
        "= Alojamiento": original, "Tipo de cambio": clp / original if original else None, "Ingreso CLP": clp,
        "Comisión (no se descuenta)": g["comision_mes"].sum(),
    })
puente = pd.DataFrame(puente)
plata = lambda t: st.column_config.NumberColumn(t, format="localized")  # noqa: E731
st.dataframe(puente, hide_index=True, width="stretch",
             column_config={"Total reservas": plata("Total reservas"), "− Limpieza": plata("− Limpieza"),
                            "= Alojamiento": plata("= Alojamiento"), "Ingreso CLP": plata("Ingreso CLP"),
                            "Tipo de cambio": st.column_config.NumberColumn("× Tipo de cambio", format="%.2f"),
                            "Comisión (no se descuenta)": plata("Comisión (no se descuenta)")})
st.caption("Montos en la moneda de la reserva y proporcionales a las noches del mes, hasta \"= Alojamiento\"; "
           f"la última columna en CLP. Suma de \"Ingreso CLP\": **{c.dinero(total, 'CLP')}**.")

sin_tc = int(fin["noches_sin_tipo_cambio"].sum())
if sin_tc:
    st.warning(f"{sin_tc} noches no tienen tipo de cambio a CLP y **no suman** al total. "
               "Agrega la tasa del mes en `tipo_cambio_mensual` (andina_lab).")

# -- Por propiedad -----------------------------------------------------------------------------------------
st.subheader("Por propiedad")
prop = (fin.groupby(["propiedad", "mercado"], sort=False)
           .agg(reservas=("id_reserva", "nunique"), noches=("noches_mes", "sum"), ingreso_clp=("ingreso_mes_clp", "sum"))
           .reset_index().sort_values("ingreso_clp", ascending=False))
prop["participacion"] = prop["ingreso_clp"] / total if total else None
fig = px.bar(prop, x="ingreso_clp", y="propiedad", color="mercado", orientation="h",
             category_orders={"propiedad": prop["propiedad"].tolist(), "mercado": c.ORDEN_MERCADOS},
             color_discrete_map=c.COLOR_MERCADO, custom_data=["noches", "reservas"])
fig.update_traces(hovertemplate="%{y}: %{x:,.0f} CLP · %{customdata[0]} noches · %{customdata[1]} reservas"
                                "<extra></extra>")
fig.update_xaxes(tickformat=",.0f")
st.plotly_chart(c.estilo_figura(fig, alto=100 + 32 * len(prop)).update_layout(hovermode="closest", separators=",."),
                width="stretch")
c.ver_tabla(prop.rename(columns={"propiedad": "Propiedad", "mercado": "Mercado", "reservas": "Reservas",
                                 "noches": "Noches", "ingreso_clp": "Ingreso CLP", "participacion": "% del total"}),
            column_config={"Ingreso CLP": plata("Ingreso CLP"),
                           "% del total": st.column_config.NumberColumn("% del total", format="percent")})

# -- Reserva por reserva --------------------------------------------------------------------------------------
st.subheader("Reserva por reserva")
st.caption("Cada fila suma su \"Ingreso CLP\" al total. Los montos de la reserva están completos (todas sus noches); "
           "\"Alojamiento del mes\" es la parte que corresponde a las noches de este mes.")
detalle = fin[["propiedad", "mercado", "canal", "numero_registro", "fecha_reserva", "llegada", "salida",
               "noches_reserva", "noches_mes", "moneda", "total_reserva", "limpieza", "ingreso_alojamiento",
               "ingreso_mes_original", "tipo_cambio", "ingreso_mes_clp", "comision"]]
st.dataframe(detalle, hide_index=True, width="stretch",
             column_config={"propiedad": "Propiedad", "mercado": "Mercado", "canal": "Canal",
                            "numero_registro": "N° reserva",
                            "fecha_reserva": st.column_config.DateColumn("Reservada", format="DD-MM-YYYY"),
                            "llegada": st.column_config.DateColumn("Llegada", format="DD-MM-YYYY"),
                            "salida": st.column_config.DateColumn("Salida", format="DD-MM-YYYY"),
                            "noches_reserva": "Noches reserva", "noches_mes": "Noches en el mes", "moneda": "Moneda",
                            "total_reserva": plata("Total reserva"), "limpieza": plata("Limpieza"),
                            "ingreso_alojamiento": plata("Alojamiento (total)"),
                            "ingreso_mes_original": plata("Alojamiento del mes"),
                            "tipo_cambio": st.column_config.NumberColumn("Tipo de cambio", format="%.2f"),
                            "ingreso_mes_clp": plata("Ingreso CLP"), "comision": plata("Comisión (total)")})
st.download_button("Descargar CSV", detalle.to_csv(index=False).encode("utf-8-sig"),
                   file_name=f"ingresos_{mes:%Y-%m}.csv", mime="text/csv")

if not canceladas.empty:
    st.markdown(f"**Canceladas, no suman** ({canceladas['id_reserva'].nunique()} con noches en este mes)")
    st.dataframe(canceladas[["propiedad", "canal", "numero_registro", "llegada", "salida", "noches_mes",
                             "moneda", "total_reserva", "status_reserva", "fecha_cancelacion"]],
                 hide_index=True, width="stretch",
                 column_config={"propiedad": "Propiedad", "canal": "Canal", "numero_registro": "N° reserva",
                                "llegada": st.column_config.DateColumn("Llegada", format="DD-MM-YYYY"),
                                "salida": st.column_config.DateColumn("Salida", format="DD-MM-YYYY"),
                                "noches_mes": "Noches en el mes", "moneda": "Moneda",
                                "total_reserva": plata("Total reserva"), "status_reserva": "Estado",
                                "fecha_cancelacion": st.column_config.DateColumn("Cancelada", format="DD-MM-YYYY")})

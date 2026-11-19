"""Inicio de la app: resumen del último mes y accesos a cada página."""
from datetime import date

import streamlit as st

from lib import bq
from lib.auth import usuario_actual
from lib.config import tabla

st.set_page_config(page_title="Finanzas por propiedad", page_icon="📊", layout="wide")
u = usuario_actual()

st.title(f"Hola, {u.nombre}")
st.caption("Rentabilidad de cada propiedad, con datos de Airbnb, cartolas y boletas.")

hoy = date.today()
mes_pasado = date(hoy.year - (hoy.month == 1), (hoy.month - 2) % 12 + 1, 1)

params = [bq.p("mes", "DATE", mes_pasado)]
filtro = ""
if u.permitidas() is not None:
    filtro = "AND propiedad_id IN UNNEST(@perm)"
    params.append(bq.pa("perm", "STRING", u.permitidas()))
resumen = bq.consultar(f"""SELECT moneda, SUM(ingresos) ingresos, SUM(gastos_totales) gastos, SUM(resultado) resultado
    FROM {tabla('pnl_mensual')} WHERE mes = @mes {filtro} GROUP BY moneda ORDER BY moneda""", params)

st.subheader(f"Resultado de {mes_pasado.strftime('%m/%Y')}")
if resumen.empty:
    st.info("Aún no hay datos confirmados para ese mes.")
for r in resumen.itertuples():
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Ingresos {r.moneda}", f"{float(r.ingresos):,.0f}".replace(",", "."))
    c2.metric(f"Gastos {r.moneda}", f"{float(r.gastos):,.0f}".replace(",", "."))
    c3.metric(f"Resultado {r.moneda}", f"{float(r.resultado):,.0f}".replace(",", "."))

if u.puede_editar:
    pend = bq.consultar(f"SELECT COUNT(*) n FROM {tabla('movimientos')} WHERE estado = 'PENDIENTE'")
    n = int(pend["n"].iloc[0])
    if n:
        st.warning(f"Hay {n} movimientos por revisar. Ve a **Pendientes** en el menú de la izquierda.")

st.markdown("""
**¿Qué hago aquí?**
1. **Cargar datos** — una vez al mes, sube el CSV de Airbnb y la cartola del banco.
2. **Registrar gasto** — saca una foto de la boleta y guárdala.
3. **Pendientes** — elige propiedad y categoría de lo que el sistema no supo clasificar.
4. **Rentabilidad** — revisa el resultado por propiedad, mes y año.
5. **Asistente** — pregunta en español, por ejemplo: *¿qué propiedad tuvo el peor margen este año?*
""")

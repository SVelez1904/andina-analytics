import streamlit as st

from lib import bq, parsers
from lib.auth import exigir_edicion, usuario_actual
from lib.clasificador import aplicar_reglas, clasificar_con_ia
from lib.importar_operaciones import importar, resumen_texto
from lib.registro import guardar_movimientos, nueva_carga_id

st.set_page_config(page_title="Cargar datos", page_icon="📥", layout="wide")
u = usuario_actual()
exigir_edicion(u)
st.title("Cargar datos")

tab_airbnb, tab_banco, tab_ops = st.tabs(["Airbnb (CSV)", "Cartola del banco", "Planillas de operaciones"])

with tab_airbnb:
    st.markdown("En Airbnb: **Menú → Ganancias → Historial de transacciones → Exportar CSV**. "
                "Puedes subir el mismo archivo dos veces: no se duplica.")
    archivo = st.file_uploader("Archivo CSV de Airbnb", type=["csv"], key="airbnb")
    if archivo and st.button("Procesar archivo de Airbnb", type="primary"):
        with st.spinner("Leyendo y guardando..."):
            try:
                df = parsers.leer_tabla(archivo.getvalue(), archivo.name)
                carga = nueva_carga_id()
                movs, info = parsers.parse_airbnb(df, bq.propiedades(), carga, u.email)
                res = guardar_movimientos(movs, "AIRBNB_CSV", archivo.name, u.email, carga, len(df))
            except ValueError as e:
                st.error(str(e))
                st.stop()
        st.success(f"Listo: {info['reservas']} reservas y {info['ajustes']} ajustes leídos. "
                   f"{res['filas_nuevas']} movimientos nuevos, {res['duplicados']} ya existían.")
        if res["pendientes"]:
            st.warning(f"{res['pendientes']} movimientos no coinciden con ninguna propiedad "
                       "(revisa el nombre del anuncio en la tabla de propiedades) y quedaron en Pendientes.")

with tab_banco:
    st.markdown("Descarga la cartola desde tu banco en **Excel o CSV** y súbela aquí. "
                "Se registran los **cargos** (gastos). Los abonos de Airbnb no se cuentan dos veces.")
    archivo_b = st.file_uploader("Cartola (Excel o CSV)", type=["csv", "xlsx", "xls"], key="banco")
    moneda = st.radio("Moneda de la cuenta", ["CLP", "BRL"], horizontal=True)
    if archivo_b:
        df_b = parsers.leer_tabla(archivo_b.getvalue(), archivo_b.name, palabra_encabezado="fecha")
        sugerido = parsers.detectar_columnas_banco(df_b)
        opciones = ["(ninguna)"] + list(df_b.columns)
        st.caption("Revisa que cada dato apunte a la columna correcta:")
        c = st.columns(5)
        mapeo = {}
        for i, (clave, etiqueta) in enumerate([("fecha", "Fecha"), ("descripcion", "Descripción"),
                                               ("cargo", "Cargo"), ("abono", "Abono"), ("monto", "Monto (si es una sola columna)")]):
            valor = sugerido.get(clave)
            sel = c[i].selectbox(etiqueta, opciones, index=opciones.index(valor) if valor in opciones else 0, key=f"m_{clave}")
            mapeo[clave] = None if sel == "(ninguna)" else sel
        st.dataframe(df_b.head(8), use_container_width=True)
        if st.button("Procesar cartola", type="primary"):
            with st.spinner("Clasificando gastos (reglas + IA)..."):
                try:
                    carga = nueva_carga_id()
                    movs = parsers.parse_banco(df_b, mapeo, moneda, carga, u.email)
                    nuevos_ids = set(movs["movimiento_id"]) - bq.ids_existentes(movs["movimiento_id"].tolist())
                    movs = movs[movs["movimiento_id"].isin(nuevos_ids)]  # no gastar IA en duplicados
                    movs = aplicar_reglas(movs, bq.reglas())
                    movs = clasificar_con_ia(movs, bq.propiedades(), bq.categorias())
                    res = guardar_movimientos(movs, "BANCO", archivo_b.name, u.email, carga, len(df_b))
                except ValueError as e:
                    st.error(str(e))
                    st.stop()
            st.success(f"Se cargaron {res['filas_nuevas']} gastos nuevos. "
                       f"{res['filas_nuevas'] - res['pendientes']} quedaron clasificados.")
            if res["pendientes"]:
                st.warning(f"{res['pendientes']} quedaron en **Pendientes** para que elijas propiedad y categoría.")

with tab_ops:
    st.markdown("Sube una o varias planillas de la carpeta **3. OPERATIONS** (Excel). El sistema reconoce solo "
                "de qué planilla se trata: gastos operacionales, control de mantenimiento, turnos de limpieza, "
                "inventario o presupuestos de reforma. Puedes volver a subirlas cuando se actualicen.")
    st.caption("Gastos y pagos de limpieza se suman al resultado de cada propiedad. Mantenimiento, inventario y "
               "turnos se usan para indicadores y alertas del informe mensual (el registro de mantenimiento no "
               "suma dinero: el gasto ya está en la planilla de gastos).")
    archivos = st.file_uploader("Planillas (.xlsx)", type=["xlsx"], accept_multiple_files=True, key="ops")
    props = bq.propiedades()["propiedad_id"].tolist()
    prop_presu = st.selectbox("Si subes un presupuesto de reforma, ¿de qué propiedad es?", ["(no aplica)"] + props)
    if archivos and st.button("Procesar planillas", type="primary"):
        for a in archivos:
            if "pessoais" in a.name.lower() or "personal" in a.name.lower():
                st.info(f"{a.name}: omitida (planilla personal, no es del negocio).")
                continue
            with st.spinner(f"Procesando {a.name}..."):
                try:
                    r = importar(a.getvalue(), a.name, u.email,
                                 propiedad_presupuesto=None if prop_presu == "(no aplica)" else prop_presu)
                except Exception as e:  # una planilla con error no detiene las demás
                    st.error(f"{a.name}: no se pudo procesar ({e}).")
                    continue
            (st.error if "error" in r else st.success)(f"**{a.name}** — {resumen_texto(r)}")

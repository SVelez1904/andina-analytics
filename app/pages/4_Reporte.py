"""Generar y descargar el reporte semanal."""
from pathlib import Path

import pandas as pd
import streamlit as st

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] if Path(__file__).parent.name == "app" else Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import comun as c
from analitica import reporte
from analitica.config import ANTHROPIC_API_KEY, MODELO_REPORTE

c.configurar("Reporte semanal")
if not c.conexion_ok():
    st.stop()

# Generar escribe en Postgres (analitica.reportes): solo se puede en tu computador.
# En Streamlit Cloud la página muestra y descarga los reportes ya subidos a BigQuery.
if c.postgres_disponible():
    con_ia = st.toggle("Redactar resumen y acciones con IA", value=bool(ANTHROPIC_API_KEY),
                       disabled=not ANTHROPIC_API_KEY,
                       help=f"Usa {MODELO_REPORTE}. Cuesta menos de 1 centavo de dólar por reporte." if ANTHROPIC_API_KEY
                       else "Agrega ANTHROPIC_API_KEY al archivo .env para activarlo.")
    if not ANTHROPIC_API_KEY:
        st.caption("Sin clave de API, el resumen se escribe con reglas fijas (las tablas son las mismas).")

    if st.button("Generar reporte de hoy", type="primary"):
        with st.spinner("Armando el reporte..."):
            r = reporte.generar(usar_ia=con_ia)
        extra = f" Redactado con {r['modelo']} (≈ {r['costo_usd']:.4f} USD)." if r["modelo"] else ""
        st.success(f"Listo: {Path(r['archivo']).name}.{extra}")
        with st.spinner("Subiendo el reporte a BigQuery..."):
            from analitica import subir_bigquery
            errores = subir_bigquery.subir(["analitica.reportes"], imprimir=lambda *_: None)
        if errores:
            st.warning("El reporte quedó en tu base local, pero no se pudo subir a BigQuery. "
                       "Corre `python -m analitica.subir_bigquery --solo analitica.reportes`.")
        c.leer.clear()
        c.existe.clear()
else:
    st.caption("Los reportes se generan en tu computador (`python -m analitica.reporte`) y se suben con "
               "`python -m analitica.subir_bigquery`. Aquí puedes verlos y descargarlos.")

if not c.requiere("analitica.reportes", c.COMO_ACTUALIZAR):
    st.stop()

hist = c.leer("""SELECT id, generado, fecha_corte, titulo, modelo_ia, archivo, contenido_md
                 FROM analitica.reportes ORDER BY generado DESC LIMIT 20""")
if hist.empty:
    st.info("Aún no hay reportes subidos. Genera uno en tu computador y súbelo a BigQuery.")
    st.stop()

st.subheader("Reportes generados")
elegido = st.selectbox("Reporte", hist["id"],
                       format_func=lambda i: (lambda r: f"{r['titulo']} · generado {pd.Timestamp(r['generado']):%d-%m %H:%M}"
                                              + (" · IA" if r["modelo_ia"] else ""))(hist.set_index("id").loc[i]))
fila = hist.set_index("id").loc[elegido]

archivo = Path(fila["archivo"]) if fila["archivo"] else None
col1, col2 = st.columns(2)
if archivo and archivo.exists():
    col1.download_button(f"Descargar {archivo.suffix[1:].upper()}", archivo.read_bytes(), file_name=archivo.name)
    html = archivo.with_suffix(".html")
    if archivo.suffix != ".html" and html.exists():
        col2.download_button("Descargar HTML", html.read_bytes(), file_name=html.name)
else:
    col1.download_button("Descargar (Markdown)", fila["contenido_md"].encode("utf-8"),
                         file_name=f"reporte_{fila['fecha_corte']}.md")
st.divider()
st.markdown(fila["contenido_md"])

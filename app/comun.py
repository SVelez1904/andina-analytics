"""Piezas compartidas del dashboard: conexión, caché, colores y formatos.

El dashboard lee de BigQuery (app/bq.py). Postgres solo se usa en tu computador para generar
reportes; los datos se copian a BigQuery con `python -m analitica.subir_bigquery`.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import auth  # noqa: E402
import bq  # noqa: E402
from analitica.config import META_INGRESO_MENSUAL_CLP, clave_mercado  # noqa: E402,F401

COMO_ACTUALIZAR = "Corre `python -m analitica.subir_bigquery` en tu computador."

# Colores (paleta validada para daltonismo). Una serie = azul; dos = azul y naranjo.
AZUL, NARANJO, AGUA = "#2a78d6", "#eb6834", "#1baf7a"
AZUL_CLARO = "#86b6ef"
SECUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
GRIS = "#c3c2b7"
ESTADO = {"Crítico": "🔴 Crítico", "Alerta": "🟠 Alerta", "OK": "🟢 OK", "Sin datos suficientes": "⚪ Sin datos suficientes"}
COLOR_MERCADO = {"Chile": AZUL, "Brasil": NARANJO}
ORDEN_MERCADOS = ["Chile", "Brasil"]   # Chile siempre primero (leyendas, columnas y listas)

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
NOMBRE_TEMA = {
    "limpieza": "Limpieza", "ropa_de_cama": "Ropa de cama", "mantenimiento": "Mantenimiento",
    "equipamiento": "Equipamiento", "cocina": "Cocina", "bano": "Baño", "climatizacion": "Climatización",
    "wifi_tv": "Wifi / TV", "privacidad": "Privacidad", "ruido": "Ruido", "seguridad": "Seguridad",
    "check_in": "Check-in", "comunicacion": "Comunicación", "ubicacion": "Ubicación",
    "precio_valor": "Precio / valor", "exactitud": "Exactitud", "espacio": "Espacio", "vista": "Vista",
    "externo": "Externo", "otro": "Otro",
}


def configurar(titulo):
    st.set_page_config(page_title=f"{titulo} · Andina Analytics", page_icon="📊", layout="wide")
    # Login ANTES de cualquier lectura: la caché de datos es compartida entre todos los usuarios del servidor
    auth.require_login()
    with st.sidebar:
        st.button("🔄 Actualizar datos", on_click=st.cache_data.clear, type="tertiary",
                  help="Vuelve a leer BigQuery ahora. Normalmente no hace falta: los datos nuevos aparecen "
                       "solos hasta 10 minutos después de correr subir_bigquery.")
    st.title(titulo)
    indicador_datos()


def frescura():
    """Cuándo se subieron los datos a BigQuery y hasta qué reserva llegan. Una consulta chica (2 columnas)."""
    df = leer("""SELECT MAX(_cargado_en) AS cargado_en, CAST(MAX(fecha_reserva) AS DATE) AS ultima_reserva
                 FROM public.vw_fct_noches""")
    return bq.cliente().project, df.iloc[0]["cargado_en"], df.iloc[0]["ultima_reserva"]


def indicador_datos():
    """Línea pequeña bajo el título: hasta qué fecha llegan los datos y cuándo se subieron a BigQuery."""
    try:
        proyecto, cargado, ultima = frescura()
    except Exception:          # sin conexión: conexion_ok() muestra el error
        return
    cargado = pd.Timestamp(cargado)
    if pd.isna(cargado):
        return
    cargado = (cargado.tz_localize("UTC") if cargado.tzinfo is None else cargado).tz_convert("America/Santiago")
    horas = (pd.Timestamp.now(tz="America/Santiago") - cargado).total_seconds() / 3600
    aviso = " · ⚠️ conviene actualizar" if horas > 24 * 7 else ""
    hasta = f"Datos hasta el **{pd.Timestamp(ultima):%d-%m-%Y}** (última reserva) · " if pd.notna(ultima) else ""
    st.caption(f"🗓️ {hasta}subidos a BigQuery el {cargado:%d-%m-%Y %H:%M}{aviso}",
               help=f"Fuente: BigQuery, proyecto `{proyecto}`. Todas las páginas leen de ahí; la fecha de subida "
                    "es la columna `_cargado_en` que agrega `python -m analitica.subir_bigquery`. "
                    "Los datos se guardan en caché y se releen solos al detectar una subida nueva "
                    "(se revisa cada 10 minutos, sin costo).")


DATASETS = ("public", "analitica")


@st.cache_data(ttl=600, show_spinner=False)
def estado_datos():
    """(versión, tablas existentes) leído de la metadata de BigQuery cada 10 minutos. No es una query: no se cobra."""
    return bq.estado(DATASETS)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _leer(sql, params, version_datos):
    # version_datos no se usa adentro: es parte de la llave de caché. Si cambia (subiste datos), se relee.
    # (No puede empezar con "_": Streamlit no usa esos argumentos en la llave.)
    return bq.leer(sql, params)


def leer(sql, params=None):
    """SELECT en BigQuery (parámetros como @nombre). Queda en caché hasta que se suban datos nuevos (máx. 12 h).
    No usar CURRENT_DATE() en el SQL: pasar la fecha con c.hoy() como parámetro, así BigQuery
    también puede usar su caché de resultados."""
    return _leer(sql, params, estado_datos()[0])


def existe(objeto):
    return objeto in estado_datos()[1]


def hoy():
    """Fecha de hoy en Chile, para pasarla como parámetro @hoy."""
    return pd.Timestamp.now(tz="America/Santiago").date()


def conexion_ok():
    """Muestra un error claro si no hay conexión; devuelve True/False."""
    try:
        estado_datos()
        return True
    except Exception as e:
        st.error("No me pude conectar a BigQuery. En Streamlit Cloud revisa Settings → Secrets "
                 "(`gcp_project` y `[gcp_service_account]`); en tu computador, `GCP_PROJECT` en el `.env` y "
                 "`gcloud auth application-default login`.\n\n"
                 f"Detalle: `{e.__class__.__name__}: {str(e)[:300]}`")
        return False


@st.cache_data(ttl=60, show_spinner=False)
def postgres_disponible():
    """True solo en tu computador, con la base local corriendo (para generar reportes)."""
    try:
        from analitica import db
        return bool(db.existe("analitica.reportes"))
    except Exception:
        return False


def chile_primero(df, columnas):
    """Ordena con Chile (CLP) antes que Brasil (BRL); orden estable para el resto."""
    if df.empty:
        return df
    return df.sort_values(columnas, key=clave_mercado, kind="stable").reset_index(drop=True)


def requiere(objeto, como_crearlo):
    if not existe(objeto):
        st.info(f"Todavía no existe `{objeto}`. {como_crearlo}")
        return False
    return True


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
       COALESCE(SUM(v.ingreso_clp), 0)                                  AS ingreso_alojamiento_clp,
       COALESCE(SUM(IF(c.es_futura, v.ingreso_local, 0)), 0)            AS ingreso_futuro,
       COALESCE(SUM(IF(c.es_futura, v.ingreso_clp, 0)), 0)              AS ingreso_futuro_clp
FROM calendario c
JOIN public.dim_propiedades pr ON pr.id_interno = c.id_propriedade
LEFT JOIN vendidas v ON v.id_propriedade = c.id_propriedade AND v.fecha = c.fecha
GROUP BY 1, 2, 3, 4, 5
ORDER BY mes
"""


def mes_completo():
    """Una fila por propiedad y mes (ver SQL_MES_COMPLETO), con `mes` como fecha de pandas."""
    kp = leer(SQL_MES_COMPLETO, {"hoy": hoy()})
    kp["mes"] = pd.to_datetime(kp["mes"])
    return kp


def resumen_mes(kp, mes):
    """Una fila por mercado para `mes`, con dos lecturas de ese mes:
    - a la fecha (`*_fecha`): solo las noches que ya ocurrieron. Se puede comparar con un mes cerrado.
    - mes completo: suma las noches futuras ya reservadas, sobre todas las noches del mes.
    En un mes cerrado no hay noches futuras, así que ambas lecturas dan lo mismo."""
    g = kp[kp["mes"] == mes].groupby(["mercado", "moneda_local"], as_index=False).agg(
        vendidas=("noches_vendidas", "sum"), disponibles=("noches_disponibles", "sum"),
        futuras=("noches_futuras_vendidas", "sum"), pasadas=("noches_pasadas", "sum"),
        ingreso=("ingreso_alojamiento", "sum"), ingreso_futuro=("ingreso_futuro", "sum"))
    vendidas_fecha = g["vendidas"] - g["futuras"]
    ingreso_fecha = g["ingreso"] - g["ingreso_futuro"]
    pasadas = g["pasadas"].where(g["pasadas"] > 0)      # el día 1 aún no ocurre ninguna noche del mes
    g["vendidas_fecha"] = vendidas_fecha
    g["ocupacion_fecha"] = vendidas_fecha / pasadas
    g["adr_fecha"] = ingreso_fecha / vendidas_fecha.where(vendidas_fecha > 0)
    g["revpar_fecha"] = ingreso_fecha / pasadas
    g["ocupacion_mes"] = g["vendidas"] / g["disponibles"].where(g["disponibles"] > 0)
    return chile_primero(g, ["mercado"])


DIAS_PARA_REVIEW = 14   # Airbnb da 14 días desde el check-out para dejar la review
# Situación de cada reserva respecto a su review. Siempre con ícono y texto, nunca solo color.
CON_REVIEW, PUEDE_DEJARLA, PLAZO_VENCIDO = "✅ Con review", "⏳ Aún puede dejarla", "⌛ Plazo vencido, sin review"
EN_CURSO, POR_LLEGAR = "🛏️ Estadía en curso", "📅 Por llegar"


def reservas_reviews():
    """Una fila por reserva no cancelada con su review (si la dejó), desde el primer mes con reviews importadas.
    Agrega terminada (ya hizo check-out) y pendiente (terminada, sin review y todavía dentro de los 14 días)."""
    df = leer("""SELECT propiedad, mercado, id_reserva, llegada, salida, mes_salida, con_review, fecha_review, nota
                 FROM analitica.vw_reservas_reviews""")
    for col in ("llegada", "salida", "mes_salida", "fecha_review"):
        df[col] = pd.to_datetime(df[col])
    if not df["con_review"].any():
        return df.iloc[0:0], None
    desde = df.loc[df["con_review"], "mes_salida"].min()   # antes no hay reviews cargadas: no se cuentan
    df = df[df["mes_salida"] >= desde].copy()
    hoy_ = pd.Timestamp(hoy())
    df["terminada"] = df["salida"] <= hoy_
    df["pendiente"] = df["terminada"] & ~df["con_review"] & ((hoy_ - df["salida"]).dt.days <= DIAS_PARA_REVIEW)
    df["situacion"] = situacion_reserva(df, hoy_)
    df["dias_restantes"] = (DIAS_PARA_REVIEW - (hoy_ - df["salida"]).dt.days).where(df["pendiente"])
    return df, desde


def situacion_reserva(df, hoy_):
    """En qué está cada reserva respecto a su review (necesita con_review, pendiente, llegada y salida)."""
    return pd.Series(np.select(
        [df["con_review"], df["pendiente"], df["salida"] <= hoy_, df["llegada"] <= hoy_],
        [CON_REVIEW, PUEDE_DEJARLA, PLAZO_VENCIDO, EN_CURSO], default=POR_LLEGAR), index=df.index)


def resumen_reviews(df, por):
    """Reservas, terminadas, con review y % con review (sobre las terminadas), agrupado por las columnas `por`
    (lista vacía = una sola fila con el total)."""
    if not por:
        df, por = df.assign(total="Total"), ["total"]
    g = df.groupby(por, as_index=False).agg(reservas=("id_reserva", "count"), terminadas=("terminada", "sum"),
                                            con_review=("con_review", "sum"), pendientes=("pendiente", "sum"),
                                            nota=("nota", "mean"))
    g["tasa"] = g["con_review"] / g["terminadas"].where(g["terminadas"] > 0)
    return g


def reviews_por_departamento(df):
    """Una fila por departamento con reservas en `df` (resumen_reviews más vencidas y por_terminar).
    Devuelve (con review, aún sin review): un departamento va al primero con una sola review,
    aunque le falten otras (ver columnas pendientes y vencidas)."""
    g = resumen_reviews(df, ["propiedad"]).merge(
        df.assign(vencida=df["situacion"].eq(PLAZO_VENCIDO), por_terminar=~df["terminada"])
          .groupby("propiedad", as_index=False)[["vencida", "por_terminar"]].sum()
          .rename(columns={"vencida": "vencidas"}), on="propiedad")
    con = g[g["con_review"] > 0].sort_values(["tasa", "con_review"], ascending=False)
    sin = g[g["con_review"] == 0].sort_values(["pendientes", "terminadas"], ascending=False)
    return con.reset_index(drop=True), sin.reset_index(drop=True)


MIN_REVIEWS_EVALUAR = 3   # con menos, una sola review decide el mes (mismo mínimo que "Sin datos suficientes")


def evaluar_reviews(df):
    """Evalúa las reviews recibidas en un mes, de todos los anuncios juntos. `df`: filas de vw_reviews_mensual de ese
    mes. Usa los umbrales de criticidad: 4,90 y 4,80, y una review de 3 o menos siempre es mal mes."""
    n = int(df["reviews_con_nota"].sum())
    nota = float(df["suma_general"].sum()) / n if n else None
    minima = df["nota_minima"].min() if n else None
    if n and minima <= 3:
        veredicto = "🔴 Mes con problemas"
    elif n < MIN_REVIEWS_EVALUAR:
        veredicto = "⚪ Aún pocas reviews"
    elif nota >= 4.9:
        veredicto = "🟢 Buen mes"
    elif nota >= 4.8:
        veredicto = "🟠 Mes regular"
    else:
        veredicto = "🔴 Mes con problemas"
    return {"reviews": n, "nota": nota, "minima": minima, "cinco": n - int(df["reviews_bajo_5"].sum()),
            "veredicto": veredicto}


def nombre_mes(d, largo=False):
    d = pd.Timestamp(d)
    return f"{MESES[d.month - 1]} {d.year}" if not largo else f"{MESES[d.month - 1]}-{str(d.year)[2:]}"


def dinero(x, moneda=""):
    if x is None or pd.isna(x):
        return "—"
    return f"{float(x):,.0f}".replace(",", ".") + (f" {moneda}" if moneda else "")


def pct(x, dec=0):
    return "—" if x is None or pd.isna(x) else f"{float(x) * 100:.{dec}f} %"


def estilo_figura(fig, alto=360, y_pct=False, leyenda=True):
    fig.update_layout(
        height=alto, margin=dict(l=8, r=8, t=36, b=8), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text="") if leyenda
        else dict(visible=False),
        font=dict(size=13),
    )
    fig.update_xaxes(showgrid=False, title_text="")
    fig.update_yaxes(gridcolor="rgba(137,135,129,0.25)", zeroline=False, title_text="")
    if y_pct:
        fig.update_yaxes(tickformat=".0%", range=[0, 1.05])
    return fig


def ver_tabla(df, titulo="Ver tabla", **kw):
    with st.expander(titulo):
        st.dataframe(df, hide_index=True, width="stretch", **kw)


# -- Colores y donas -------------------------------------------------------------------------------------
# Paleta categórica validada (orden fijo, nunca se "cicla" más allá de 8)
CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
# Estados (siempre acompañados de ícono + texto, nunca solo color)
BIEN, CERCA, LEJOS = "#0ca30c", "#fab219", "#d03b3b"
PISTA = "rgba(137,135,129,0.18)"   # el "fondo" de las donas


def estado_meta(indice):
    """indice = valor / meta. Devuelve (color, etiqueta)."""
    if indice is None or pd.isna(indice):
        return GRIS, "— sin dato"
    if indice >= 1:
        return BIEN, "✅ En meta"
    if indice >= 0.7:
        return CERCA, "⚠️ Cerca"
    return LEJOS, "🔴 Lejos"


def colores_por_nombre(nombres):
    """Color fijo por nombre (orden alfabético), para que no cambie al filtrar el ranking."""
    orden = sorted(set(nombres))
    return {n: CATEGORICA[i % len(CATEGORICA)] for i, n in enumerate(orden)}


def dona(fig, fraccion, color, centro, sub="", fila=None, col=None, nombre=""):
    """Agrega una dona tipo 'medidor' (fracción 0-1 rellena) a fig. Con fila/col va en una grilla."""
    f = 0.0 if fraccion is None or pd.isna(fraccion) else max(0.0, min(1.0, float(fraccion)))
    kw = dict(row=fila, col=col) if fila else {}
    fig.add_pie(values=[f, 1 - f], hole=0.72, sort=False, direction="clockwise", rotation=0,
                marker=dict(colors=[color, PISTA], line=dict(width=0)), textinfo="none",
                hoverinfo="skip", showlegend=False, name=nombre, **kw)
    return fig


def grilla_donas(items, columnas=4, alto_fila=210):
    """items: lista de dicts {titulo, fraccion, color, centro, sub}. Devuelve una figura con donas."""
    from plotly.subplots import make_subplots
    n = len(items)
    columnas = max(1, min(columnas, n))
    filas = -(-n // columnas)
    fig = make_subplots(rows=filas, cols=columnas, specs=[[{"type": "domain"}] * columnas] * filas,
                        subplot_titles=[it["titulo"] for it in items], vertical_spacing=0.16 / max(filas, 1) + 0.06)
    for i, it in enumerate(items):
        dona(fig, it["fraccion"], it["color"], it["centro"], fila=i // columnas + 1, col=i % columnas + 1)
    # Textos al centro de cada dona
    for i, it in enumerate(items):
        dom = fig.data[i].domain
        x = (dom.x[0] + dom.x[1]) / 2
        y = (dom.y[0] + dom.y[1]) / 2
        fig.add_annotation(x=x, y=y + 0.02 / filas, xref="paper", yref="paper", showarrow=False,
                           text=f"<b>{it['centro']}</b>", font=dict(size=20))
        if it.get("sub"):
            fig.add_annotation(x=x, y=y - 0.09 / filas, xref="paper", yref="paper", showarrow=False,
                               text=it["sub"], font=dict(size=11, color="#898781"))
    fig.update_layout(height=alto_fila * filas + 30, margin=dict(l=8, r=8, t=40, b=8), showlegend=False)
    for a in fig.layout.annotations[:n]:          # títulos de cada dona
        a.update(font=dict(size=13))
    return fig
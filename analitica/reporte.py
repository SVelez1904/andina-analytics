"""
Reporte semanal del negocio: ingresos vs meta, KPIs, pronóstico, noches en riesgo, reviews, conversión y controles.

Las tablas y cifras se calculan siempre desde la base (no las inventa la IA).
Si hay ANTHROPIC_API_KEY, Claude Haiku escribe el resumen y las acciones de la semana a partir
de esas cifras; si no, se escriben con reglas fijas.

Uso (desde la carpeta andina_analytics):
    python -m analitica.reporte                 # genera HTML (y PDF si está weasyprint) en reportes/
    python -m analitica.reporte --sin-ia        # sin llamar a la API
    python -m analitica.reporte --no-guardar    # no lo registra en analitica.reportes

Antes conviene correr:  python -m analitica.pronostico --guardar   y   python -m analitica.reviews_ia
"""

import argparse
import json
from datetime import date

import pandas as pd

from . import db
from .config import (ANTHROPIC_API_KEY, CARPETA_REPORTES, META_INGRESO_MENSUAL_CLP, MODELO_REPORTE, clave_mercado,
                     estado_meta, precio)

NOMBRE_TEMA = {
    "limpieza": "Limpieza", "ropa_de_cama": "Ropa de cama", "mantenimiento": "Mantenimiento",
    "equipamiento": "Equipamiento", "cocina": "Cocina", "bano": "Baño", "climatizacion": "Climatización",
    "wifi_tv": "Wifi / TV", "privacidad": "Privacidad", "ruido": "Ruido", "seguridad": "Seguridad",
    "check_in": "Check-in", "comunicacion": "Comunicación", "ubicacion": "Ubicación",
    "precio_valor": "Precio / valor", "exactitud": "Exactitud del anuncio", "espacio": "Espacio",
    "vista": "Vista", "externo": "Externo", "otro": "Otro",
}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]


# -- Formatos -----------------------------------------------------------------------------

def nombre_mes(d):
    d = pd.Timestamp(d)
    return f"{MESES[d.month - 1]} {d.year}"


def pct(x):
    return "—" if x is None or pd.isna(x) else f"{float(x):.0%}"


def dinero(x, moneda=""):
    if x is None or pd.isna(x):
        return "—"
    return f"{float(x):,.0f}".replace(",", ".") + (f" {moneda}" if moneda else "")


def pp(x):
    return "—" if x is None or pd.isna(x) else f"{float(x) * 100:+.1f} pp"


def txt(x, vacio="—"):
    return vacio if x is None or (not isinstance(x, (list, tuple)) and pd.isna(x)) or str(x).strip() == "" else str(x)


def pct_airbnb(x, dec=1):
    """Las tasas de Airbnb se guardan como porcentaje (1.38 = 1,38 %)."""
    return "—" if x is None or pd.isna(x) else f"{float(x):.{dec}f} %"


def tabla_md(df, columnas):
    """columnas: lista de (titulo, funcion_que_recibe_la_fila)."""
    if df is None or df.empty:
        return "_Sin datos._\n"
    lineas = ["| " + " | ".join(t for t, _ in columnas) + " |",
              "|" + "|".join("---" for _ in columnas) + "|"]
    for _, r in df.iterrows():
        lineas.append("| " + " | ".join(str(f(r)).replace("|", "/").replace("\n", " ") for _, f in columnas) + " |")
    return "\n".join(lineas) + "\n"


def chile_primero(df, columnas):
    """Ordena con Chile (CLP) antes que Brasil (BRL); orden estable para el resto."""
    if df.empty:
        return df
    return df.sort_values(columnas, key=clave_mercado, kind="stable").reset_index(drop=True)


def _leer_si_existe(objeto, sql, params=None):
    if not db.existe(objeto):
        return pd.DataFrame()
    try:
        return db.leer(sql, params)
    except Exception:
        return pd.DataFrame()


# -- Datos ------------------------------------------------------------------------------------

def reunir(corte=None):
    """Junta todo lo que va en el reporte. Devuelve un dict de DataFrames."""
    corte = pd.Timestamp(corte or date.today()).date()
    d = {"corte": corte}

    # Ingreso por alojamiento (CLP; Brasil convertido) de los últimos 6 meses cerrados y el mes en curso.
    # El mes en curso cuenta también las noches futuras ya reservadas ("on the books").
    d["ingresos"] = _leer_si_existe("public.vw_fct_noches", """
        SELECT CAST(date_trunc('month', fecha) AS date)  AS mes,
               COALESCE(SUM(ingreso_noche_clp), 0)       AS ingreso_clp
        FROM public.vw_fct_noches
        WHERE vendida
          AND fecha >= date_trunc('month', CAST(:c AS date)) - interval '6 months'
          AND fecha <  date_trunc('month', CAST(:c AS date)) + interval '1 month'
        GROUP BY 1 ORDER BY 1""", {"c": corte})

    d["kpis_mercado"] = _leer_si_existe("public.vw_kpis_mercado_mensual", """
        SELECT * FROM public.vw_kpis_mercado_mensual
        WHERE mes >= (date_trunc('month', CAST(:c AS date)) - interval '13 months') AND mes <= :c
        ORDER BY mercado, mes""", {"c": corte})
    d["kpis_mercado"] = chile_primero(d["kpis_mercado"], ["mercado", "mes"])

    d["kpis_propiedad"] = _leer_si_existe("public.vw_kpis_mensuales", """
        SELECT propiedad, mercado, moneda_local, mes, ocupacion, adr, revpar, noches_vendidas, noches_disponibles
        FROM public.vw_kpis_mensuales
        WHERE mes_cerrado AND mes = (SELECT MAX(mes) FROM public.vw_kpis_mensuales WHERE mes_cerrado AND mes <= :c)
        ORDER BY mercado, ocupacion DESC NULLS LAST""", {"c": corte})
    d["kpis_propiedad"] = chile_primero(d["kpis_propiedad"], ["mercado"])

    d["pronostico"] = _leer_si_existe("analitica.vw_pronostico_actual", """
        SELECT fecha_corte, propiedad, mes, moneda, disponibles, reservadas_ya, noches_pronostico,
               ingreso_pronostico, ocupacion_ya, ocupacion_pronostico
        FROM analitica.vw_pronostico_actual ORDER BY mes, ocupacion_pronostico DESC""")
    d["pronostico"] = chile_primero(d["pronostico"], ["mes", "moneda"])

    d["riesgo"] = _leer_si_existe("analitica.vw_noches_en_riesgo", """
        SELECT propiedad,
               COUNT(*)                                         AS noches_libres,
               COUNT(*) FILTER (WHERE dias_para_la_noche <= 7)  AS libres_7_dias,
               ROUND(AVG(probabilidad), 3)                      AS prob_media,
               MIN(fecha)                                       AS primera_libre
        FROM analitica.vw_noches_en_riesgo
        GROUP BY propiedad ORDER BY libres_7_dias DESC, noches_libres DESC""")

    d["reviews"] = _leer_si_existe("public.vw_reviews_actual", """
        SELECT propiedad, reviews_mes, reviews_3m, promedio_3m, reviews_acumuladas, promedio_acumulado,
               peor_categoria_3m, peor_nota_3m, criticidad, motivo
        FROM public.vw_reviews_actual
        ORDER BY CASE criticidad WHEN 'Crítico' THEN 1 WHEN 'Alerta' THEN 2 WHEN 'OK' THEN 3 ELSE 4 END,
                 promedio_acumulado""")

    d["pendientes"] = _leer_si_existe("analitica.vw_pendientes_propiedad", """
        SELECT propiedad, tema, menciones, reviews, prioridad, severidad_maxima, ultima_mencion,
               citas, acciones_sugeridas
        FROM analitica.vw_pendientes_propiedad ORDER BY prioridad DESC, ultima_mencion DESC LIMIT 10""")

    d["conversion"] = _leer_si_existe("public.vw_scorecard_mensual", """
        SELECT propiedad, mes, foto_desde, foto_hasta, conversion_general, impresiones_primera_pagina,
               busqueda_a_anuncio, anuncio_a_reserva, cuello_de_botella, criticidad
        FROM public.vw_scorecard_mensual
        WHERE mes = (SELECT MAX(mes) FROM public.vw_scorecard_mensual WHERE conversion_general IS NOT NULL)
          AND conversion_general IS NOT NULL
        ORDER BY conversion_general""")

    d["controles"] = _leer_si_existe("public.vw_controles_calidad", """
        SELECT n, control, resultado, estado, prioridad FROM public.vw_controles_calidad
        WHERE estado <> 'OK' ORDER BY prioridad, n""")
    return d


def resumen_numeros(d):
    """Versión compacta (JSON) de los datos: es lo único que ve la IA."""
    out = {"fecha_corte": str(d["corte"])}
    im = ingresos_vs_meta(d)
    if not im.empty:
        def kpi(r):
            return {"mes": nombre_mes(r["mes"]), "ingreso_clp": round(float(r["ingreso_clp"])),
                    "cumplimiento_meta": round(float(r["cumplimiento"]), 3), "estado": r["estado"],
                    "diferencia_clp": round(float(r["diferencia"]))}
        cerrados = im[~im["en_curso"]]
        out["ingresos_vs_meta"] = {"meta_mensual_clp": round(META_INGRESO_MENSUAL_CLP)}
        if not cerrados.empty:
            out["ingresos_vs_meta"]["ultimo_mes_cerrado"] = kpi(cerrados.iloc[-1])
            out["ingresos_vs_meta"]["meses_cerrados_en_meta"] = (f"{int((cerrados['cumplimiento'] >= 1).sum())} "
                                                                  f"de {len(cerrados)}")
        if im["en_curso"].any():
            out["ingresos_vs_meta"]["mes_en_curso_reservado_a_la_fecha"] = kpi(im[im["en_curso"]].iloc[-1])
    km = d["kpis_mercado"]
    if not km.empty:
        out["kpis_por_mercado"] = []
        for mercado, g in km.groupby("mercado", sort=False):
            cerrados = g[g["mes_cerrado"]].sort_values("mes")
            if cerrados.empty:
                continue
            ult = cerrados.iloc[-1]
            ant = cerrados.iloc[-2] if len(cerrados) > 1 else None
            hace_un_ano = g[pd.to_datetime(g["mes"]) == pd.Timestamp(ult["mes"]) - pd.DateOffset(years=1)]
            out["kpis_por_mercado"].append({
                "mercado": mercado, "moneda": ult["moneda_local"], "mes": nombre_mes(ult["mes"]),
                "ocupacion": round(float(ult["ocupacion"] or 0), 3), "adr": round(float(ult["adr"] or 0)),
                "revpar": round(float(ult["revpar"] or 0)),
                "ocupacion_mes_anterior": None if ant is None else round(float(ant["ocupacion"] or 0), 3),
                "revpar_mes_anterior": None if ant is None else round(float(ant["revpar"] or 0)),
                "revpar_mismo_mes_ano_anterior": None if hace_un_ano.empty else round(float(hace_un_ano.iloc[0]["revpar"] or 0)),
            })
    pr = d["pronostico"]
    if not pr.empty:
        out["pronostico_por_mes"] = [
            {"mes": nombre_mes(m), "moneda": mon,
             "ocupacion_reservada_ya": round(g["reservadas_ya"].sum() / g["disponibles"].sum(), 3),
             "ocupacion_pronosticada": round(g["noches_pronostico"].sum() / g["disponibles"].sum(), 3),
             "ingreso_pronosticado": round(float(g["ingreso_pronostico"].sum()))}
            for (m, mon), g in pr.groupby(["mes", "moneda"], sort=False)]
        mes_actual = pr["mes"].min()
        bajas = pr[(pr["mes"] == mes_actual)].nsmallest(3, "ocupacion_pronostico")
        out["propiedades_con_menor_pronostico_este_mes"] = [
            {"propiedad": r.propiedad, "ocupacion_pronosticada": round(float(r.ocupacion_pronostico), 3)}
            for r in bajas.itertuples()]
    if not d["riesgo"].empty:
        out["noches_libres_proximos_7_dias"] = {r.propiedad: int(r.libres_7_dias)
                                                for r in d["riesgo"].itertuples() if r.libres_7_dias}
    rv = d["reviews"]
    if not rv.empty:
        out["reviews_criticas_o_alerta"] = [
            {"propiedad": r.propiedad, "criticidad": r.criticidad, "motivo": r.motivo,
             "promedio_acumulado": None if pd.isna(r.promedio_acumulado) else float(r.promedio_acumulado),
             "peor_categoria_3m": r.peor_categoria_3m}
            for r in rv.itertuples() if r.criticidad in ("Crítico", "Alerta")]
    if not d["pendientes"].empty:
        out["pendientes_operativos_90_dias"] = [
            {"propiedad": r.propiedad, "tema": NOMBRE_TEMA.get(r.tema, r.tema), "menciones": int(r.menciones),
             "prioridad": int(r.prioridad), "acciones_sugeridas": list(r.acciones_sugeridas or [])[:2],
             "cita": (list(r.citas or []) or [""])[0]}
            for r in d["pendientes"].head(6).itertuples()]
    if not d["conversion"].empty:
        out["conversion_airbnb"] = [
            {"propiedad": r.propiedad, "conversion_general_pct": None if pd.isna(r.conversion_general) else float(r.conversion_general),
             "cuello_de_botella": r.cuello_de_botella}
            for r in d["conversion"].itertuples()]
    if not d["controles"].empty:
        out["controles_de_datos_a_revisar"] = [f"{r.control}: {r.resultado}" for r in d["controles"].itertuples()]
    return _sin_nan(out)


def ingresos_vs_meta(d):
    """Una fila por mes: ingreso CLP, meta, cumplimiento (ingreso / meta), diferencia y estado."""
    im = d.get("ingresos", pd.DataFrame())
    if im.empty:
        return im
    im = im.copy()
    im["mes"] = pd.to_datetime(im["mes"])
    im["ingreso_clp"] = pd.to_numeric(im["ingreso_clp"]).fillna(0)
    im["meta"] = META_INGRESO_MENSUAL_CLP
    im["cumplimiento"] = im["ingreso_clp"] / im["meta"]
    im["diferencia"] = im["ingreso_clp"] - im["meta"]
    im["estado"] = im["cumplimiento"].map(estado_meta)
    im["en_curso"] = im["mes"] >= pd.Timestamp(d["corte"]).replace(day=1)
    return im.sort_values("mes").reset_index(drop=True)


def _sin_nan(x):
    """NaN/NaT -> None, para que el JSON sea válido."""
    if isinstance(x, dict):
        return {k: _sin_nan(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_sin_nan(v) for v in x]
    try:
        if x is not None and not isinstance(x, (str, bool)) and pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    return x


# -- Textos -----------------------------------------------------------------------------------

SISTEMA_REPORTE = """Eres el analista de una empresa chilena de arriendo de corto plazo (Airbnb) con \
departamentos en Santiago y Pucón y una casa en Porto Seguro (Brasil).
Recibes un JSON con las cifras de la semana. Escribe en español de Chile, claro y directo, para la dueña.
Reglas estrictas:
- Usa SOLO las cifras del JSON. No inventes números, causas ni propiedades.
- Ocupación en porcentaje (0.756 -> 76 %). Montos con separador de miles y su moneda.
- Si un dato falta, no lo menciones.
- El KPI de rendimiento financiero es el ingreso mensual vs la meta (ingresos_vs_meta): la primera viñeta
  del Resumen siempre es ese KPI (cumplimiento en % y cuánto falta o sobra en CLP).
- Al hablar de mercados, Chile siempre va antes que Brasil.
Formato de salida (Markdown, sin títulos de nivel 1 ni 2):
**Resumen** — 3 a 5 viñetas con lo más importante (KPI financiero, desempeño del último mes cerrado, pronóstico, riesgos).
**Acciones de la semana** — 3 a 6 viñetas numeradas, concretas, ordenadas por impacto, cada una con la
propiedad y el porqué (ej. noches libres próximas, review crítica, cuello de botella de conversión)."""


def texto_por_reglas(n):
    res, acc = [], []
    im = n.get("ingresos_vs_meta", {})
    meta = im.get("meta_mensual_clp")
    if "ultimo_mes_cerrado" in im:
        k = im["ultimo_mes_cerrado"]
        res.append(f"- **KPI financiero**, {k['mes']}: ingreso {dinero(k['ingreso_clp'], 'CLP')} = "
                   f"{k['cumplimiento_meta']:.0%} de la meta de {dinero(meta, 'CLP')} (**{k['estado']}**, "
                   f"{'sobran' if k['diferencia_clp'] >= 0 else 'faltaron'} {dinero(abs(k['diferencia_clp']), 'CLP')}). "
                   f"Meses en meta: {im.get('meses_cerrados_en_meta', '—')}.")
    if "mes_en_curso_reservado_a_la_fecha" in im:
        k = im["mes_en_curso_reservado_a_la_fecha"]
        res.append(f"- {k['mes'].capitalize()} (en curso): {dinero(k['ingreso_clp'], 'CLP')} ya reservados, "
                   f"{k['cumplimiento_meta']:.0%} de la meta"
                   + (f"; faltan {dinero(-k['diferencia_clp'], 'CLP')}." if k["diferencia_clp"] < 0 else "; meta cubierta."))
        if k["diferencia_clp"] < 0:
            acc.append(f"Faltan {dinero(-k['diferencia_clp'], 'CLP')} para la meta de {k['mes']}: priorizar las "
                       f"noches libres de las próximas semanas.")
    for k in n.get("kpis_por_mercado", []):
        var = ""
        if k.get("revpar_mes_anterior"):
            cambio = k["revpar"] / k["revpar_mes_anterior"] - 1
            var = f" ({cambio:+.0%} vs. el mes anterior)"
        res.append(f"- **{k['mercado']}**, {k['mes']}: ocupación {k['ocupacion']:.0%}, "
                   f"ADR {dinero(k['adr'], k['moneda'])}, RevPAR {dinero(k['revpar'], k['moneda'])}{var}.")
    for p in n.get("pronostico_por_mes", [])[:2]:
        res.append(f"- Pronóstico {p['mes']} ({p['moneda']}): {p['ocupacion_pronosticada']:.0%} de ocupación "
                   f"(ya reservado {p['ocupacion_reservada_ya']:.0%}), ingreso estimado {dinero(p['ingreso_pronosticado'], p['moneda'])}.")
    criticas = [r for r in n.get("reviews_criticas_o_alerta", []) if r["criticidad"] == "Crítico"]
    if criticas:
        res.append("- Reviews en estado **Crítico**: " + ", ".join(r["propiedad"] for r in criticas) + ".")

    libres = sorted(n.get("noches_libres_proximos_7_dias", {}).items(), key=lambda x: -x[1])
    for prop, q in libres[:2]:
        acc.append(f"**{prop}**: {q} noches libres en los próximos 7 días. Revisar precio mínimo y "
                   f"estadía mínima en PriceLabs.")
    for r in criticas[:2]:
        acc.append(f"**{r['propiedad']}**: reviews en estado crítico ({r['motivo']}). "
                   f"Peor categoría: {txt(r.get('peor_categoria_3m'))}.")
    for p in n.get("pendientes_operativos_90_dias", [])[:2]:
        accion = p["acciones_sugeridas"][0] if p["acciones_sugeridas"] else f"Revisar {p['tema'].lower()}"
        acc.append(f"**{p['propiedad']}**: {accion} ({p['menciones']} menciones de {p['tema'].lower()} en 90 días).")
    for c in n.get("conversion_airbnb", [])[:1]:
        acc.append(f"**{c['propiedad']}**: la conversión más baja del portafolio. {c['cuello_de_botella']}.")
    if n.get("controles_de_datos_a_revisar"):
        acc.append(f"Revisar {len(n['controles_de_datos_a_revisar'])} controles de calidad de datos antes de "
                   f"confiar en las cifras.")
    texto = "**Resumen**\n\n" + ("\n".join(res) or "- Sin datos suficientes.") + "\n\n**Acciones de la semana**\n\n"
    texto += "\n".join(f"{i}. {a}" for i, a in enumerate(acc[:6], 1)) or "Sin acciones urgentes."
    return texto + "\n"


def texto_con_ia(n, cliente=None):
    """Devuelve (texto, modelo, tokens_in, tokens_out)."""
    if cliente is None:
        import anthropic
        cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = cliente.messages.create(
        model=MODELO_REPORTE, max_tokens=1200, system=SISTEMA_REPORTE,
        messages=[{"role": "user", "content": "Cifras de la semana:\n" + json.dumps(n, ensure_ascii=False, default=str)}],
    )
    texto = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    return texto + "\n", MODELO_REPORTE, resp.usage.input_tokens, resp.usage.output_tokens


# -- Armado -------------------------------------------------------------------------------------

def armar_markdown(d, texto):
    corte = d["corte"]
    md = [f"# Reporte semanal · {corte:%d-%m-%Y}\n", texto]

    md.append("\n## 1. Rendimiento financiero: ingresos vs meta\n")
    im = ingresos_vs_meta(d)
    md.append(f"Meta: **{dinero(META_INGRESO_MENSUAL_CLP, 'CLP')} al mes** de ingreso por alojamiento "
              f"(todo el portafolio; Brasil convertido a CLP).\n\n")
    if im.empty:
        md.append("_Sin datos de ingresos._\n")
    else:
        cerrados, curso = im[~im["en_curso"]], im[im["en_curso"]]
        if not cerrados.empty:
            r = cerrados.iloc[-1]
            md.append(f"- **{nombre_mes(r['mes']).capitalize()}** (último mes cerrado): {dinero(r['ingreso_clp'], 'CLP')} "
                      f"→ **{pct(r['cumplimiento'])} de la meta** · {r['estado']}. "
                      f"Meses en meta: {int((cerrados['cumplimiento'] >= 1).sum())} de {len(cerrados)}.\n")
        if not curso.empty:
            r = curso.iloc[-1]
            md.append(f"- **{nombre_mes(r['mes']).capitalize()}** (en curso, reservado a la fecha): "
                      f"{dinero(r['ingreso_clp'], 'CLP')} → **{pct(r['cumplimiento'])} de la meta**"
                      + (f" · faltan {dinero(-r['diferencia'], 'CLP')}.\n" if r["diferencia"] < 0 else " · meta cubierta.\n"))
        md.append("\n" + tabla_md(im, [
            ("Mes", lambda r: nombre_mes(r["mes"]) + (" (en curso)" if r["en_curso"] else "")),
            ("Ingreso", lambda r: dinero(r["ingreso_clp"], "CLP")), ("Meta", lambda r: dinero(r["meta"], "CLP")),
            ("Cumplimiento", lambda r: pct(r["cumplimiento"])),
            ("Diferencia", lambda r: ("+" if r["diferencia"] >= 0 else "-") + dinero(abs(r["diferencia"]), "CLP")),
            ("Estado", lambda r: r["estado"])]))
        md.append("\n_Estado: En meta ≥ 100 % · Cerca ≥ 70 % · Lejos < 70 %. El mes en curso incluye las noches "
                  "futuras ya reservadas y todavía puede subir._\n")

    md.append("\n## 2. Desempeño del último mes cerrado\n")
    km = d["kpis_mercado"]
    if not km.empty:
        md.append(tabla_md(km[km["mes_cerrado"]].sort_values(["mercado", "mes"], ascending=[True, False], key=clave_mercado)
                           .groupby("mercado", sort=False).head(3), [
            ("Mercado", lambda r: r["mercado"]), ("Mes", lambda r: nombre_mes(r["mes"])),
            ("Ocupación", lambda r: pct(r["ocupacion"])), ("ADR", lambda r: dinero(r["adr"], r["moneda_local"])),
            ("RevPAR", lambda r: dinero(r["revpar"], r["moneda_local"])),
            ("Noches vendidas", lambda r: f"{int(r['noches_vendidas'])} de {int(r['noches_disponibles'])}")]))
    if not d["kpis_propiedad"].empty:
        md.append(f"\nPor propiedad ({nombre_mes(d['kpis_propiedad']['mes'].iloc[0])}):\n\n")
        md.append(tabla_md(d["kpis_propiedad"], [
            ("Propiedad", lambda r: r["propiedad"]), ("Ocupación", lambda r: pct(r["ocupacion"])),
            ("ADR", lambda r: dinero(r["adr"], r["moneda_local"])),
            ("RevPAR", lambda r: dinero(r["revpar"], r["moneda_local"]))]))

    md.append("\n## 3. Pronóstico de ocupación\n")
    pr = d["pronostico"]
    if pr.empty:
        md.append("_No hay pronóstico guardado. Corre `python -m analitica.pronostico --guardar`._\n")
    else:
        fc = pd.Timestamp(pr["fecha_corte"].iloc[0])
        if (pd.Timestamp(corte) - fc).days > 7:
            md.append(f"> Ojo: el pronóstico es del {fc:%d-%m-%Y}. Vuelve a correrlo para actualizarlo.\n\n")
        resumen = (pr.groupby(["mes", "moneda"], sort=False)
                   .agg(disp=("disponibles", "sum"), ya=("reservadas_ya", "sum"),
                        pron=("noches_pronostico", "sum"), ingreso=("ingreso_pronostico", "sum")).reset_index())
        md.append(tabla_md(resumen, [
            ("Mes", lambda r: nombre_mes(r["mes"])), ("Moneda", lambda r: r["moneda"]),
            ("Reservado hoy", lambda r: pct(r["ya"] / r["disp"])),
            ("Pronóstico", lambda r: pct(r["pron"] / r["disp"])),
            ("Ingreso estimado", lambda r: dinero(r["ingreso"], r["moneda"]))]))
        md.append("\n_Método pickup: aún no considera temporada, así que diciembre-febrero pueden salir bajos._\n")

    md.append("\n## 4. Noches libres en los próximos 21 días\n")
    md.append(tabla_md(d["riesgo"], [
        ("Propiedad", lambda r: r["propiedad"]), ("Libres (7 días)", lambda r: int(r["libres_7_dias"])),
        ("Libres (21 días)", lambda r: int(r["noches_libres"])),
        ("Prob. media de venderse", lambda r: pct(r["prob_media"])),
        ("Primera libre", lambda r: pd.Timestamp(r["primera_libre"]).strftime("%d-%m"))]))

    md.append("\n## 5. Reviews\n")
    md.append(tabla_md(d["reviews"], [
        ("Propiedad", lambda r: r["propiedad"]), ("Estado", lambda r: r["criticidad"]),
        ("Prom. acumulado", lambda r: "—" if pd.isna(r["promedio_acumulado"]) else f"{r['promedio_acumulado']:.2f}"),
        ("Prom. 3 meses", lambda r: "—" if pd.isna(r["promedio_3m"]) else f"{r['promedio_3m']:.2f}"),
        ("Peor categoría 3m", lambda r: txt(r["peor_categoria_3m"])), ("Motivo", lambda r: txt(r["motivo"], ""))]))
    if not d["pendientes"].empty:
        md.append("\nPendientes según los comentarios (últimos 90 días, clasificados con IA):\n\n")
        md.append(tabla_md(d["pendientes"], [
            ("Propiedad", lambda r: r["propiedad"]), ("Tema", lambda r: NOMBRE_TEMA.get(r["tema"], r["tema"])),
            ("Menciones", lambda r: int(r["menciones"])), ("Prioridad", lambda r: int(r["prioridad"])),
            ("Qué dijo el huésped", lambda r: (list(r["citas"] or []) or [""])[0]),
            ("Acción sugerida", lambda r: (list(r["acciones_sugeridas"] or []) or [""])[0])]))

    md.append("\n## 6. Conversión en Airbnb\n")
    cv = d["conversion"]
    if not cv.empty:
        r0 = cv.iloc[0]
        md.append(f"Foto del {pd.Timestamp(r0['foto_desde']):%d-%m} al {pd.Timestamp(r0['foto_hasta']):%d-%m-%Y}.\n\n")
    md.append(tabla_md(cv, [
        ("Propiedad", lambda r: r["propiedad"]), ("Conversión", lambda r: pct_airbnb(r["conversion_general"], 2)),
        ("1ª página", lambda r: pct_airbnb(r["impresiones_primera_pagina"], 0)),
        ("Búsqueda → anuncio", lambda r: pct_airbnb(r["busqueda_a_anuncio"], 1)),
        ("Anuncio → reserva", lambda r: pct_airbnb(r["anuncio_a_reserva"], 1)),
        ("Cuello de botella", lambda r: txt(r["cuello_de_botella"]))]))

    md.append("\n## 7. Controles de calidad de datos\n")
    if d["controles"].empty:
        md.append("Todos los controles en OK.\n")
    else:
        md.append(tabla_md(d["controles"], [("Control", lambda r: r["control"]),
                                            ("Resultado", lambda r: r["resultado"]),
                                            ("Estado", lambda r: r["estado"])]))
    return "\n".join(md)


CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: "Helvetica Neue", Arial, sans-serif; color: #1f2328; font-size: 10.5pt; line-height: 1.45;
       max-width: 960px; margin: 0 auto; padding: 16px; background: #ffffff; }
h1 { font-size: 19pt; margin: 0 0 12px; color: #0b3d5c; }
h2 { font-size: 13pt; margin: 22px 0 8px; color: #0b3d5c; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 10px; font-size: 9pt; }
th, td { border-bottom: 1px solid #e5e7eb; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #f3f5f7; font-weight: 600; }
td:not(:first-child) { font-variant-numeric: tabular-nums; }
blockquote { margin: 6px 0; padding: 6px 10px; background: #fff8e6; border-left: 3px solid #d19a00; }
em { color: #57606a; }
"""


def a_html(md_texto, titulo):
    import markdown
    cuerpo = markdown.markdown(md_texto, extensions=["tables"])
    return (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>{titulo}</title>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'><style>{CSS}</style></head>"
            f"<body>{cuerpo}</body></html>")


def generar(corte=None, usar_ia=True, guardar_en_base=True, cliente=None, carpeta=None, pdf=True):
    d = reunir(corte)
    n = resumen_numeros(d)
    modelo, t_in, t_out = None, None, None
    if usar_ia and (ANTHROPIC_API_KEY or cliente is not None):
        try:
            texto, modelo, t_in, t_out = texto_con_ia(n, cliente)
        except Exception as e:
            print(f"  No se pudo usar la IA ({e}); se usa el texto por reglas.")
            texto = texto_por_reglas(n)
    else:
        texto = texto_por_reglas(n)

    titulo = f"Reporte semanal {d['corte']:%d-%m-%Y}"
    md_texto = armar_markdown(d, texto)
    if modelo:
        md_texto += f"\n\n_Resumen y acciones redactados por {modelo} a partir de las tablas de este reporte._\n"

    carpeta = carpeta or CARPETA_REPORTES
    carpeta.mkdir(parents=True, exist_ok=True)
    base = carpeta / f"reporte_{d['corte']:%Y-%m-%d}"
    html = a_html(md_texto, titulo)
    base.with_suffix(".html").write_text(html, encoding="utf-8")
    archivo = base.with_suffix(".html")
    if pdf:
        try:
            from weasyprint import HTML
            HTML(string=html).write_pdf(base.with_suffix(".pdf"))
            archivo = base.with_suffix(".pdf")
        except Exception as e:  # weasyprint no instalado o sin librerías del sistema
            print(f"  PDF no generado ({e.__class__.__name__}); queda el HTML.")

    if guardar_en_base:
        with db.transaccion() as con:
            db.ejecutar(con, """
                INSERT INTO analitica.reportes (fecha_corte, titulo, contenido_md, datos, modelo_ia,
                                                tokens_entrada, tokens_salida, archivo)
                VALUES (:c, :t, :md, CAST(:datos AS jsonb), :m, :ti, :to, :a)""",
                        {"c": d["corte"], "t": titulo, "md": md_texto,
                         "datos": json.dumps(n, ensure_ascii=False, default=str),
                         "m": modelo, "ti": t_in, "to": t_out, "a": str(archivo)})
    costo = None
    if modelo:
        p_in, p_out = precio(modelo)
        costo = t_in / 1e6 * p_in + t_out / 1e6 * p_out
    return {"markdown": md_texto, "html": html, "archivo": archivo, "modelo": modelo, "costo_usd": costo,
            "numeros": n}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Genera el reporte semanal.")
    ap.add_argument("--fecha-corte", default=None, help="AAAA-MM-DD (por defecto, hoy)")
    ap.add_argument("--sin-ia", action="store_true", help="No llama a la API; texto por reglas.")
    ap.add_argument("--no-guardar", action="store_true", help="No lo registra en analitica.reportes.")
    ap.add_argument("--sin-pdf", action="store_true")
    a = ap.parse_args(argv)
    r = generar(a.fecha_corte, usar_ia=not a.sin_ia, guardar_en_base=not a.no_guardar, pdf=not a.sin_pdf)
    extra = f" · IA: {r['modelo']} ≈ {r['costo_usd']:.4f} USD" if r["modelo"] else " · texto por reglas"
    print(f"✅ Reporte en {r['archivo']}{extra}")


if __name__ == "__main__":
    main()

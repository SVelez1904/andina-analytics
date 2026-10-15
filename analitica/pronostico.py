"""
Pronóstico de ocupación e ingresos por propiedad y mes (método "pickup").

    pronóstico = noches ya reservadas
               + noches libres × probabilidad histórica de que se reserven
                 con esa anticipación (días entre hoy y la noche)

La curva de pickup se aprende de tus reservas; cada propiedad se ajusta según cómo se
vendió en los últimos 120 días (con suavizado cuando hay pocos datos).

Uso (desde la carpeta andina_analytics):
    python -m analitica.pronostico                 # desde hoy, 3 meses, muestra en pantalla
    python -m analitica.pronostico --guardar       # además lo guarda en analitica.* (dashboard y reporte)
    python -m analitica.pronostico --backtest      # ¿qué tan bien acierta con meses pasados?
    python -m analitica.pronostico --csv pronostico.csv

Limitaciones: no conoce cancelaciones futuras ni bloqueos, ni la temporada (todavía).
"""

import argparse
import calendar
from datetime import date, datetime

import numpy as np
import pandas as pd

from . import db
from .config import CONFIABLE_DESDE

MAX_LEAD = 120
SUAVIZADO_PROP = 30.0
DIAS_FACTOR = 120
TRAMOS = [0, 3, 7, 14, 21, 30, 45, 60, 90, MAX_LEAD + 1]


def a_fecha(s):
    return datetime.strptime(s, "%Y-%m-%d").date() if isinstance(s, str) else s


def fin_de_mes(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


# -- Datos ------------------------------------------------------------------------------

def cargar():
    df = db.leer("""
        SELECT n.id_propriedade, p.nome_anuncio, n.fecha, n.vendida, n.fecha_reserva,
               n.ingreso_noche_local, n.moneda_local
        FROM public.vw_fct_noches n
        JOIN public.dim_propiedades p ON p.id_interno = n.id_propriedade
    """)
    if df.empty:
        raise SystemExit("public.vw_fct_noches está vacía: importa reservas en andina_lab y ejecuta sql/vw_kpis.sql.")
    bajas_df = db.leer("SELECT id_propriedade, fecha_baja FROM public.propiedad_fechas WHERE fecha_baja IS NOT NULL")
    return preparar(df), dict(zip(bajas_df["id_propriedade"], pd.to_datetime(bajas_df["fecha_baja"])))


def preparar(df):
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["fecha_reserva"] = pd.to_datetime(df["fecha_reserva"])
    df["vendida"] = df["vendida"].astype(bool)
    df["ingreso_noche_local"] = pd.to_numeric(df["ingreso_noche_local"], errors="coerce")
    return df


# -- Curva de pickup ----------------------------------------------------------------------

def curva(df, corte, confiable):
    """P(se reserva | libre L días antes) por anticipación L, aprendida solo con noches < corte."""
    corte, confiable = pd.Timestamp(corte), pd.Timestamp(confiable)
    hist = df[df["fecha"] < corte]
    t = hist["fecha"].values.astype("datetime64[D]")
    reservada = hist["fecha_reserva"].values.astype("datetime64[D]")
    vendida = hist["vendida"].values.astype(bool)
    prop = hist["id_propriedade"].values
    reciente = t >= np.datetime64((corte - pd.Timedelta(days=DIAS_FACTOR)).date())
    libres = np.zeros(MAX_LEAD + 1)
    tomadas = np.zeros(MAX_LEAD + 1)
    libres_p, tomadas_p = {}, {}
    for L in range(MAX_LEAD + 1):
        punto = t - np.timedelta64(L, "D")
        valido = punto >= np.datetime64(confiable.date())
        libre = valido & ~(vendida & (reservada <= punto))
        tomada = libre & vendida & (reservada > punto)
        libres[L], tomadas[L] = libre.sum(), tomada.sum()
        for p in np.unique(prop[libre & reciente]):
            m = (prop == p) & reciente
            libres_p.setdefault(p, np.zeros(MAX_LEAD + 1))[L] = (libre & m).sum()
            tomadas_p.setdefault(p, np.zeros(MAX_LEAD + 1))[L] = (tomada & m).sum()

    tasa = np.full(MAX_LEAD + 1, np.nan)
    for a, b in zip(TRAMOS[:-1], TRAMOS[1:]):
        l, tm = libres[a:b].sum(), tomadas[a:b].sum()
        if l:
            tasa[a:b] = tm / l
    tasa = pd.Series(tasa).ffill().bfill().fillna(0).values
    tasa = np.maximum.accumulate(tasa)  # más anticipación = más tiempo para venderse

    factores = {}
    for p in libres_p:
        esperado = float((libres_p[p] * tasa).sum())
        real = float(tomadas_p[p].sum())
        factores[p] = (real + SUAVIZADO_PROP) / (esperado + SUAVIZADO_PROP)
    return tasa, factores, int(libres.sum())


# -- Pronóstico -----------------------------------------------------------------------------

def pronosticar(df, bajas, corte, meses=3, confiable=CONFIABLE_DESDE):
    """Devuelve (por_mes, por_noche, tasa, n_obs)."""
    corte = a_fecha(corte)
    confiable = a_fecha(confiable)
    tasa, factores, n_obs = curva(df, corte, confiable)
    corte_ts = pd.Timestamp(corte)
    punto = corte_ts - pd.Timedelta(days=1)          # se conoce hasta ayer
    inicio_mes = pd.Timestamp(corte.replace(day=1))
    fin = pd.Timestamp(fin_de_mes((inicio_mes + pd.DateOffset(months=meses - 1)).date()))

    altas = df.groupby("id_propriedade")["fecha"].min()
    nombres = df.groupby("id_propriedade")["nome_anuncio"].first()
    monedas = df.groupby("id_propriedade")["moneda_local"].first()
    rec = df[(df["fecha"] < corte_ts) & (df["fecha"] >= corte_ts - pd.Timedelta(days=90))
             & df["vendida"] & (df["fecha_reserva"] <= punto)]
    adr = rec.groupby("id_propriedade")["ingreso_noche_local"].mean()

    conocido = df[(df["fecha"] >= inicio_mes) & (df["fecha"] <= fin)]
    estado = {(r.id_propriedade, r.fecha): r for r in conocido.itertuples(index=False)}

    filas = []
    for p in altas.index:
        desde = max(inicio_mes, altas[p])
        hasta = min(fin, bajas[p]) if p in bajas else fin
        if desde > hasta:
            continue
        f_p = factores.get(p, 1.0)
        adr_p = float(adr[p]) if p in adr.index and pd.notna(adr[p]) else 0.0
        for noche in pd.date_range(desde, hasta, freq="D"):
            r = estado.get((p, noche))
            if r is not None and r.vendida:
                # incluye las reservas creadas el mismo día del corte (las que importaste hoy)
                ya = True if noche < corte_ts else bool(pd.notna(r.fecha_reserva) and r.fecha_reserva <= corte_ts)
            else:
                ya = False
            ingreso_ya = float(r.ingreso_noche_local) if ya and r is not None and pd.notna(r.ingreso_noche_local) else 0.0
            if noche < corte_ts:
                prob = 1.0 if ya else 0.0
            else:
                prob = 1.0 if ya else min(1.0, float(tasa[min((noche - punto).days, MAX_LEAD)]) * f_p)
            filas.append((p, noche.date(), noche.to_period("M").to_timestamp().date(), ya, prob,
                          ingreso_ya, ingreso_ya if ya else prob * adr_p))

    noches = pd.DataFrame(filas, columns=["id_propriedade", "fecha", "mes", "reservada", "probabilidad",
                                          "ingreso_ya", "ingreso_esperado"])
    if noches.empty:
        return noches, noches, tasa, n_obs
    mes = noches.groupby(["id_propriedade", "mes"]).agg(
        disponibles=("probabilidad", "size"), reservadas_ya=("reservada", "sum"),
        noches_pronostico=("probabilidad", "sum"), ingreso_ya=("ingreso_ya", "sum"),
        ingreso_pronostico=("ingreso_esperado", "sum")).reset_index()
    mes["propiedad"] = mes["id_propriedade"].map(nombres)
    mes["moneda"] = mes["id_propriedade"].map(monedas)
    mes["ocupacion_ya"] = mes["reservadas_ya"] / mes["disponibles"]
    mes["ocupacion_pronostico"] = mes["noches_pronostico"] / mes["disponibles"]
    mes["factor_propiedad"] = mes["id_propriedade"].map(factores).fillna(1.0)
    noches["propiedad"] = noches["id_propriedade"].map(nombres)
    return mes, noches, tasa, n_obs


def guardar(mes, noches, corte):
    """Guarda el pronóstico en analitica.pronostico_ocupacion y analitica.pronostico_noches."""
    corte = a_fecha(corte)
    with db.transaccion() as con:
        db.ejecutar(con, "DELETE FROM analitica.pronostico_ocupacion WHERE fecha_corte = :c", {"c": corte})
        db.ejecutar(con, "DELETE FROM analitica.pronostico_noches WHERE fecha_corte = :c", {"c": corte})
        filas_mes = [{"c": corte, "p": r.id_propriedade, "m": r.mes, "d": int(r.disponibles),
                      "ya": int(r.reservadas_ya), "np": round(float(r.noches_pronostico), 2),
                      "iy": round(float(r.ingreso_ya), 2), "ip": round(float(r.ingreso_pronostico), 2),
                      "mon": r.moneda, "f": round(float(r.factor_propiedad), 3)} for r in mes.itertuples()]
        if filas_mes:
            db.ejecutar(con, """
                INSERT INTO analitica.pronostico_ocupacion
                    (fecha_corte, id_propriedade, mes, disponibles, reservadas_ya, noches_pronostico,
                     ingreso_ya, ingreso_pronostico, moneda, factor_propiedad)
                VALUES (:c, :p, :m, :d, :ya, :np, :iy, :ip, :mon, :f)""", filas_mes)
        futuras = noches[pd.to_datetime(noches["fecha"]) >= pd.Timestamp(corte)]
        filas_noche = [{"c": corte, "p": r.id_propriedade, "f": r.fecha, "r": bool(r.reservada),
                        "pr": round(float(r.probabilidad), 4)} for r in futuras.itertuples()]
        if filas_noche:
            db.ejecutar(con, """
                INSERT INTO analitica.pronostico_noches (fecha_corte, id_propriedade, fecha, reservada, probabilidad)
                VALUES (:c, :p, :f, :r, :pr)""", filas_noche)
    return len(filas_mes), len(filas_noche)


# -- Backtest -------------------------------------------------------------------------------

def backtest(df, bajas, confiable=CONFIABLE_DESDE):
    """Pronostica meses pasados (como si fuera el día 1 y el 15) y compara con lo real."""
    confiable = a_fecha(confiable)
    ultima = df["fecha_reserva"].max().date()
    d = (pd.Timestamp(confiable) + pd.Timedelta(days=45) + pd.offsets.MonthBegin(0)).date()
    filas = []
    while fin_de_mes(d) < ultima:
        for c in (d, d.replace(day=15)):
            pron, _, _, _ = pronosticar(df, bajas, c, 1, confiable)
            m = df[df["fecha"].dt.to_period("M") == pd.Period(c, "M")]
            real = m.groupby("id_propriedade")["vendida"].sum()
            for r in pron.itertuples():
                filas.append({"corte": c, "propiedad": r.propiedad, "disponibles": r.disponibles,
                              "reservadas_ya": r.reservadas_ya, "pronostico": r.noches_pronostico,
                              "real": float(real.get(r.id_propriedade, 0))})
        d = (pd.Timestamp(d) + pd.DateOffset(months=1)).date()
    return pd.DataFrame(filas)


# -- CLI --------------------------------------------------------------------------------------

def _imprimir(mes, tasa, corte, n_obs):
    print(f"\nPronóstico al {corte:%d-%m-%Y} (aprendido de {n_obs:,} observaciones de noches libres)")
    print("Probabilidad de que una noche libre se reserve, según días de anticipación:")
    print("  " + " · ".join(f"{a}-{b - 1}d: {tasa[a]:.0%}" for a, b in zip(TRAMOS[:-1], TRAMOS[1:])))
    for m, g in mes.groupby("mes"):
        print(f"\n{m:%m-%Y}")
        print(f"  {'Propiedad':38s} {'Reservado':>10s} {'Pronóstico':>11s} {'Ingreso pronosticado':>22s}")
        for _, r in g.sort_values("ocupacion_pronostico", ascending=False).iterrows():
            ingreso = (f"{r['ingreso_pronostico']:>18,.0f} {r['moneda']}" if r["ingreso_pronostico"] > 0
                       else f"{'sin precio reciente':>22s}")
            print(f"  {str(r['propiedad'])[:38]:38s} {r['ocupacion_ya']:>10.0%} {r['ocupacion_pronostico']:>11.0%}"
                  f" {ingreso}")
        for moneda, gm in g.groupby("moneda"):
            print(f"  {'Total ' + str(moneda):38s} {gm['reservadas_ya'].sum() / gm['disponibles'].sum():>10.0%}"
                  f" {gm['noches_pronostico'].sum() / gm['disponibles'].sum():>11.0%}"
                  f" {gm['ingreso_pronostico'].sum():>18,.0f} {moneda}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pronóstico de ocupación (pickup).")
    ap.add_argument("--fecha-corte", default=None, help="AAAA-MM-DD (por defecto, hoy)")
    ap.add_argument("--meses", type=int, default=3)
    ap.add_argument("--guardar", action="store_true", help="Guarda en el esquema analitica")
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--csv", default=None)
    a = ap.parse_args(argv)

    df, bajas = cargar()
    if a.backtest:
        bt = backtest(df, bajas)
        if bt.empty:
            raise SystemExit("No hay meses cerrados suficientes para el backtest.")
        print("\nBacktest: pronóstico del mes hecho el día 1 y el 15, contra lo real")
        print(f"  {'Corte':11s} {'Reservado':>10s} {'Pronóstico':>11s} {'Real':>7s} {'Error':>8s} {'Error sin pronóstico':>21s}")
        for c, g in bt.groupby("corte"):
            d = g["disponibles"].sum()
            ya, pr, re_ = g["reservadas_ya"].sum() / d, g["pronostico"].sum() / d, g["real"].sum() / d
            print(f"  {c:%d-%m-%Y} {ya:>10.0%} {pr:>11.0%} {re_:>7.0%} {pr - re_:>+8.1%} {ya - re_:>+21.1%}")
        e_p = ((bt["pronostico"] - bt["real"]) / bt["disponibles"]).abs().mean()
        e_y = ((bt["reservadas_ya"] - bt["real"]) / bt["disponibles"]).abs().mean()
        print(f"\n  Error medio por propiedad: pronóstico {e_p:.1%} · solo lo reservado {e_y:.1%}")
        return

    corte = a_fecha(a.fecha_corte) if a.fecha_corte else date.today()
    ultima = df["fecha_reserva"].max()
    if pd.notna(ultima) and (pd.Timestamp(corte) - ultima).days > 7:
        print(f"  Ojo: la reserva más reciente se creó el {ultima:%d-%m-%Y}. "
              f"Si faltan reservas recientes, el pronóstico saldrá bajo.")
    mes, noches, tasa, n_obs = pronosticar(df, bajas, corte, a.meses)
    _imprimir(mes, tasa, corte, n_obs)
    if a.csv:
        mes.to_csv(a.csv, index=False)
        print(f"\nGuardado en {a.csv}")
    if a.guardar:
        n_m, n_n = guardar(mes, noches, corte)
        print(f"\n✅ Guardado en analitica: {n_m} filas por mes, {n_n} noches futuras.")


if __name__ == "__main__":
    main()
"""Informe mensual automático. Se ejecuta como Cloud Run Job (lo dispara Cloud Scheduler el día 5).
Lee las vistas de BigQuery, Claude redacta el análisis y se envía por email.

Variables: INFORME_PARA (emails separados por coma), SMTP_USUARIO (tu Gmail),
SMTP_PASSWORD (contraseña de aplicación de Gmail, desde Secret Manager), ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import os
import smtplib
import sys
from datetime import date
from decimal import Decimal
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic  # noqa: E402

from lib import bq  # noqa: E402
from lib.config import MODELO_CLAUDE, tabla  # noqa: E402


def _primer_dia_mes_anterior(hoy: date) -> date:
    return date(hoy.year - (hoy.month == 1), (hoy.month - 2) % 12 + 1, 1)


def datos(mes: date) -> str:
    mes_ant = _primer_dia_mes_anterior(mes)
    mismo_mes_anio_ant = date(mes.year - 1, mes.month, 1)
    params = [bq.p("m", "DATE", mes), bq.p("ma", "DATE", mes_ant), bq.p("ml", "DATE", mismo_mes_anio_ant)]
    pnl = bq.consultar(f"""SELECT mes, propiedad_id, propiedad, modelo_negocio, moneda, ingresos, comisiones,
            gastos_operativos, mantenimiento, gastos_fijos, gastos_totales, resultado, margen, ocupacion, adr
        FROM {tabla('pnl_mensual')} WHERE mes IN (@m, @ma, @ml) ORDER BY moneda, propiedad_id, mes""", params)
    acumulado = bq.consultar(f"""SELECT propiedad_id, moneda, ingresos, gastos_totales, resultado, margen, roi_anual
        FROM {tabla('pnl_anual')} WHERE anio = @a ORDER BY moneda, resultado DESC""",
        [bq.p("a", "INT64", mes.year)])
    pend = bq.consultar(f"""SELECT moneda, COUNT(*) n, SUM(monto) monto FROM {tabla('movimientos')}
        WHERE estado = 'PENDIENTE' GROUP BY moneda""")
    ops = bq.consultar(f"""SELECT * FROM {tabla('operaciones_mensual')} WHERE mes IN (@m, @ma)
        ORDER BY propiedad_id, mes""", params[:2])
    alertas = bq.consultar(f"""SELECT tipo, COUNT(*) n, STRING_AGG(CONCAT(IFNULL(propiedad_id, 'bodega'), ': ', detalle), ' | ' LIMIT 8) ejemplos
        FROM {tabla('alertas_operacion')} GROUP BY tipo""")
    sin_pagar = bq.consultar(f"""SELECT COUNT(*) n, SUM(monto) monto FROM {tabla('movimientos')}
        WHERE referencia = 'SIN PAGAR' AND estado = 'OK'""")
    conv = lambda df: df.map(lambda v: float(v) if isinstance(v, Decimal) else v).to_csv(index=False)  # noqa: E731
    return (f"MES ANALIZADO: {mes:%Y-%m}\n\nP&L MENSUAL (mes analizado, mes anterior y mismo mes del año pasado):\n"
            f"{conv(pnl)}\nACUMULADO DEL AÑO:\n{conv(acumulado)}\nPENDIENTES SIN CLASIFICAR:\n{conv(pend)}"
            f"\nOPERACIONES POR PROPIEDAD (mes analizado y anterior):\n{conv(ops)}"
            f"\nALERTAS VIGENTES:\n{conv(alertas)}\nGASTOS REGISTRADOS SIN PAGAR:\n{conv(sin_pagar)}")


PROMPT = """Eres el analista financiero de un negocio de arriendos de corto plazo. Con los datos CSV de abajo,
escribe un informe mensual en español para la dueña y su jefa (sin conocimientos técnicos). Máximo 450 palabras.
Estructura:
1. Resumen en 2 frases (resultado total por moneda; nunca sumes CLP con BRL).
2. Mejores y peores propiedades del mes (resultado y margen), y su comparación con el mes anterior y el mismo mes del año pasado.
3. Alertas: márgenes negativos, gastos de mantenimiento inusuales, caídas de ocupación o ADR mayores a 20 %.
4. Acumulado del año y ROI de las propiedades que tienen inversión registrada.
5. Operaciones: mantenimientos del mes (urgentes, daños de huésped cobrables, noches bloqueadas, días para
   resolver), aseos por propiedad y propiedades cuyo gasto de mantenimiento subió frente al mes anterior.
6. Alertas para actuar: preventivas vencidas o sin registro, stock para comprar, mantenciones abiertas,
   gastos sin pagar. Máximo 5 puntos, los más importantes primero.
7. Si hay pendientes sin clasificar, advierte que las cifras pueden cambiar.
Usa solo los números de los datos. Formato CLP: 1.234.567; BRL: 1.234,56.

DATOS:
{datos}"""


def main() -> None:
    mes = _primer_dia_mes_anterior(date.today())
    texto_datos = datos(mes)
    resp = anthropic.Anthropic().messages.create(
        model=MODELO_CLAUDE, max_tokens=1500,
        messages=[{"role": "user", "content": PROMPT.format(datos=texto_datos)}])
    informe = "".join(b.text for b in resp.content if b.type == "text")

    para = [e.strip() for e in os.environ["INFORME_PARA"].split(",") if e.strip()]
    usuario = os.environ["SMTP_USUARIO"]
    msg = MIMEText(informe, "plain", "utf-8")
    msg["Subject"] = f"Informe de rentabilidad — {mes:%m/%Y}"
    msg["From"] = usuario
    msg["To"] = ", ".join(para)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(usuario, os.environ["SMTP_PASSWORD"])
        s.sendmail(usuario, para, msg.as_string())
    print(f"Informe {mes:%Y-%m} enviado a {para}")


if __name__ == "__main__":
    main()

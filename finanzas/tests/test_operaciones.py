"""Pruebas de las planillas de operaciones con libros sintéticos (misma estructura que las reales,
datos inventados): los datos del negocio nunca se suben al repositorio."""
from datetime import datetime

import openpyxl
import pandas as pd

from lib import operaciones as op

MAPA = op.MapaPropiedades(pd.DataFrame({
    "alias": ["Encina 911", "Pucón 403", "Boho 509"],
    "propiedad_id": ["ENCINA-911", "PUCON-403", "BOHO-509"],
}))


def _gastos_wb():
    wb = openpyxl.Workbook()
    wb.active.title = "RESUMEN 2026"
    for mes in ["ENE", "SEP"]:
        ws = wb.create_sheet(mes)
        ws["B1"] = f"GASTOS OPERACIONALES · {mes} 2026"
        ws.append([])
        ws.append([None, None, "MANTENCIÓN (MANO DE OBRA)"])
        ws.append([])
        ws.append([None, "▼ Escriba aquí abajo."])
        ws.append([None, "Fecha", "Categoría", "Depto", "Descripción del gasto", "Cantidad", "Valor (CLP)", "¿Pagado?", "Observaciones"])
    ws = wb["SEP"]
    ws.append([None, datetime(2026, 9, 2), "Lavandería", "Varios deptos", "Lavandería sábanas", 36, 35000, None, None])
    ws.append([None, datetime(2026, 9, 3), "Mantención (mano de obra)", "Encina 911", "Abrir puerta", None, 20000, "NO", None])
    ws.append([None, None, "Insumos", "Pucón 403", "Sin fecha", None, 10000, None, "Sin fecha en planilla"])
    ws.append([None, datetime(2026, 9, 5), "Otros", "Depto Nuevo", "Algo", None, 5000, "SI", None])
    wb.create_sheet("LISTAS")
    return wb


def test_detecta_y_lee_gastos():
    wb = _gastos_wb()
    assert op.detectar_tipo(wb) == "GASTOS"
    df, info = op.parse_gastos(wb, MAPA, "c", "yo")
    assert info["gastos"] == 4 and info["total_clp"] == 70000
    assert info["sin_pagar"] == 1 and info["fechas_estimadas"] == 1
    assert info["sin_propiedad"] == ["Depto Nuevo"]
    fila = df[df.descripcion.str.startswith("Lavandería")].iloc[0]
    assert fila.propiedad_id == "GENERAL" and fila.categoria == "lavanderia"
    sin_fecha = df[df.descripcion.str.startswith("Sin fecha")].iloc[0]
    assert str(sin_fecha.fecha) == "2026-09-01" and sin_fecha.categoria == "amenities"
    assert df[df.propiedad_id.isna()].iloc[0].estado == "PENDIENTE"
    df2, _ = op.parse_gastos(_gastos_wb(), MAPA, "c2", "yo")
    assert list(df.movimiento_id) == list(df2.movimiento_id)  # recargar no duplica


def _mant_wb():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Registro"
    ws.append(["Registro de mantenimientos"])
    ws.append(["texto"])
    ws.append(["REGISTRO"])
    ws.append(["ID", "Fecha del reporte", "Propiedad", "Ambiente", "Categoría", "Ítem / Equipo",
               "Descripción del problema / trabajo", "Tipo", "Prioridad", "Origen del reporte", "Realizado por",
               "Fecha de ejecución", "Estado", "Días hasta resolver", "Costo materiales", "Costo mano de obra",
               "Costo total", "¿Bloqueó reservas?", "Noches bloqueadas", "¿Cobrable al huésped?", "Código de reserva / huésped"])
    ws.append([])
    ws.append(["MT-0001", datetime(2026, 10, 1), "Encina 911", "Cocina", "Eléctrica", "horno", "No prende",
               "Correctiva", "Urgente", "Reporte de huésped", "Técnico", datetime(2026, 10, 2), "Completado", 1,
               None, None, 30, "Sí", 1, "No", "HMX"])
    ws.append([None, datetime(2026, 10, 8), "Boho 509", "Baño", "Plomería", "sifón", "Gotea", "Daño de huésped",
               "Alta", "Inspección de limpieza", "Otro", None, "Pendiente", None, None, None, None, "No", 0, "Sí", None])
    wp = wb.create_sheet("Preventivas")
    wp.append(["Plan de mantenimiento preventivo"])
    wp.append(["Propiedad", "Tarea preventiva", "Categoría", "Frecuencia (días)", "Última ejecución",
               "Próxima fecha", "Días restantes", "Estado", "Responsable habitual", "Notas"])
    wp.append(["Encina 911", "Filtros A/C", "Aire acondicionado", 90, "SIN REGISTRO", None, None, "SIN REGISTRO"])
    return wb


def test_mantenimiento():
    wb = _mant_wb()
    assert op.detectar_tipo(wb) == "MANTENIMIENTO"
    m, p, info = op.parse_mantenimiento(wb, MAPA, "c")
    assert info["mantenimientos"] == 2 and info["preventivas"] == 1 and info["preventivas_sin_registro"] == 1
    a = m[m.mantenimiento_id == "MT-0001"].iloc[0]
    assert a.propiedad_id == "ENCINA-911" and a.bloqueo_reservas and a.noches_bloqueadas == 1
    b = m[m.propiedad_id == "BOHO-509"].iloc[0]
    assert b.mantenimiento_id.startswith("MT-SINID-") and bool(b.cobrable_huesped)


def _limpieza_wb():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planilha1"
    ws.append([None] * 5 + ["LIMPIEZA SEMANA"])
    ws.append([None] * 7 + [datetime(2026, 11, 16 + i) for i in range(7)])
    ws.append([None] * 4 + ["Depto", "Dirección", "Barrio", "LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"])
    ws.append([None] * 3 + [1, "ENCINA 911", "dir", "Prov", "x", None, None, "x", None, None, None])
    ws.append([None] * 3 + [2, "PUCON 403 ", "dir", None, None, "x", None, None, None, None, None])
    wm = wb.create_sheet("limpeza meninas")
    wm.append([None, None, None, 30000, None, "N DE ASEOS CHICAS ", "Valor a pagar"])
    wm.append([None, None, None, 20000, None, datetime(2026, 10, 1)])
    wm.append([None, None, None, "30 por aseo ", "Javiera pucon 403", 5, 150000])
    wm.append([None, None, None, "30 por aseo ", "Bexi encina", 10, 300000])
    wm.append([None, None, None, None, None, "GASTOS DE SETEMBRO "])
    wm.append([None, None, None, "MANTENIMIENTO ", "GASTOS ANDINA ", 345000])
    return wb


def test_turnos_y_pagos_limpieza():
    wb = _limpieza_wb()
    assert op.detectar_tipo(wb) == "LIMPIEZA"
    aseos, info = op.parse_turnos(wb, MAPA, "c")
    assert info["aseos"] == 3 and set(aseos.propiedad_id) == {"ENCINA-911", "PUCON-403"}
    assert str(aseos[aseos.propiedad_id == "PUCON-403"].iloc[0].fecha) == "2026-11-17"
    equipo = pd.DataFrame([{"nombre": "Javiera", "propiedades": ["PUCON-403"]},
                           {"nombre": "Bexi", "propiedades": ["ENCINA-911", "BOHO-509"]}])
    pagos, info = op.parse_pagos_limpieza(wb, equipo, {"ENCINA-911": 3, "BOHO-509": 1}, "c", "yo")
    assert info["total_clp"] == 450000 and str(info["mes"]) == "2026-10-01"
    bexi = pagos[pagos.descripcion.str.contains("Bexi")].set_index("propiedad_id").monto
    assert bexi["ENCINA-911"] == 225000 and bexi["BOHO-509"] == 75000  # 3:1 según reservas


def test_presupuesto():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Presupuesto de trabajo"])
    ws.append(["Descripcion", "Total Materiales ", "Total Mano de obra", "Total"])
    ws.append(["Pintura", 145000, 270000, 415000])
    ws.append([None, None, "Neto", 415000])
    ws.append([None, None, "Iva(19%)", 78850])
    ws.append([None, None, "Total", 493850])
    assert op.detectar_tipo(wb) == "PRESUPUESTO"
    df, info = op.parse_presupuesto(wb, "BOHO-509", "Presupuesto.xlsx", "c")
    assert info == {"neto": 415000, "total": 493850}
    assert df.iloc[0].estado == "PRESUPUESTO" and df.iloc[0].propiedad_id == "BOHO-509"


def test_planilla_desconocida():
    wb = openpyxl.Workbook()
    wb.active.title = "Gastos mes"
    assert op.detectar_tipo(wb) == "DESCONOCIDO"

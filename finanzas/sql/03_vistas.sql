-- =====================================================================
-- 03_vistas.sql — Vistas de rentabilidad (P&L). Aquí se calculan TODOS los números.
-- La app, el asistente de Claude, el informe mensual y Looker Studio leen solo estas vistas.
-- =====================================================================

-- Movimientos confirmados con su grupo de categoría y el nombre de la propiedad
CREATE OR REPLACE VIEW `TU_PROYECTO.finanzas.v_movimientos` AS
SELECT
  mv.movimiento_id,
  mv.fecha,
  DATE_TRUNC(mv.fecha, MONTH)  AS mes,
  EXTRACT(YEAR FROM mv.fecha)  AS anio,
  mv.propiedad_id,
  p.nombre                     AS propiedad,
  p.modelo_negocio,
  mv.tipo,
  mv.categoria,
  c.grupo,
  mv.monto,
  IF(mv.tipo = 'INGRESO', mv.monto, -mv.monto) AS monto_con_signo,
  mv.moneda,
  mv.descripcion,
  mv.referencia,
  mv.noches,
  mv.fuente
FROM `TU_PROYECTO.finanzas.movimientos` mv
JOIN `TU_PROYECTO.finanzas.categorias`  c USING (categoria)
JOIN `TU_PROYECTO.finanzas.propiedades` p USING (propiedad_id)
WHERE mv.estado = 'OK';

-- Inversión total por propiedad = inversión inicial + reformas/compras EJECUTADAS
CREATE OR REPLACE VIEW `TU_PROYECTO.finanzas.v_inversion` AS
SELECT
  p.propiedad_id,
  IFNULL(p.inversion_inicial, 0) + IFNULL(SUM(IF(i.estado = 'EJECUTADO', i.monto_total, 0)), 0) AS inversion_total,
  IFNULL(SUM(IF(i.estado = 'PRESUPUESTO', i.monto_total, 0)), 0)                            AS presupuestos_pendientes
FROM `TU_PROYECTO.finanzas.propiedades` p
LEFT JOIN `TU_PROYECTO.finanzas.inversiones` i USING (propiedad_id)
GROUP BY p.propiedad_id, p.inversion_inicial;

-- P&L mensual por propiedad y moneda
CREATE OR REPLACE VIEW `TU_PROYECTO.finanzas.pnl_mensual` AS
WITH base AS (
  SELECT
    propiedad_id, propiedad, modelo_negocio, moneda, mes, anio,
    SUM(IF(tipo = 'INGRESO', monto, 0))                    AS ingresos,
    SUM(IF(categoria = 'reserva_airbnb', monto, 0))        AS ingresos_reservas,
    SUM(IF(grupo = 'COMISION', monto, 0))                  AS comisiones,
    SUM(IF(grupo = 'OPERATIVO', monto, 0))                 AS gastos_operativos,
    SUM(IF(grupo = 'MANTENIMIENTO', monto, 0))             AS mantenimiento,
    SUM(IF(grupo = 'FIJO', monto, 0))                      AS gastos_fijos,
    SUM(IF(grupo = 'IMPUESTO', monto, 0))                  AS impuestos,
    SUM(IF(grupo = 'PROPIETARIO', monto, 0))               AS liquidacion_propietario,
    SUM(IF(tipo = 'GASTO', monto, 0))                      AS gastos_totales,
    SUM(IF(categoria = 'reserva_airbnb', noches, 0))       AS noches_vendidas,
    COUNT(DISTINCT IF(categoria = 'reserva_airbnb', referencia, NULL)) AS reservas
  FROM `TU_PROYECTO.finanzas.v_movimientos`
  GROUP BY propiedad_id, propiedad, modelo_negocio, moneda, mes, anio
)
SELECT
  b.*,
  b.ingresos - b.gastos_totales                                        AS resultado,
  SAFE_DIVIDE(b.ingresos - b.gastos_totales, b.ingresos)               AS margen,
  SAFE_DIVIDE(b.ingresos_reservas, b.noches_vendidas)                  AS adr,
  SAFE_DIVIDE(b.noches_vendidas, EXTRACT(DAY FROM LAST_DAY(b.mes)))    AS ocupacion,
  SAFE_DIVIDE(b.ingresos - b.gastos_totales, NULLIF(v.inversion_total, 0)) AS roi_mensual
FROM base b
JOIN `TU_PROYECTO.finanzas.v_inversion` v USING (propiedad_id);

-- P&L anual por propiedad y moneda (con ROI anual sobre la inversión inicial)
CREATE OR REPLACE VIEW `TU_PROYECTO.finanzas.pnl_anual` AS
SELECT
  m.propiedad_id, m.propiedad, m.modelo_negocio, m.moneda, m.anio,
  COUNT(DISTINCT m.mes)            AS meses_con_datos,
  SUM(m.ingresos)                  AS ingresos,
  SUM(m.comisiones)                AS comisiones,
  SUM(m.gastos_operativos)         AS gastos_operativos,
  SUM(m.mantenimiento)             AS mantenimiento,
  SUM(m.gastos_fijos)              AS gastos_fijos,
  SUM(m.impuestos)                 AS impuestos,
  SUM(m.liquidacion_propietario)   AS liquidacion_propietario,
  SUM(m.gastos_totales)            AS gastos_totales,
  SUM(m.resultado)                 AS resultado,
  SAFE_DIVIDE(SUM(m.resultado), SUM(m.ingresos))          AS margen,
  SUM(m.noches_vendidas)           AS noches_vendidas,
  SAFE_DIVIDE(SUM(m.ingresos_reservas), SUM(m.noches_vendidas)) AS adr,
  ANY_VALUE(v.inversion_total)     AS inversion_total,
  SAFE_DIVIDE(SUM(m.resultado), NULLIF(ANY_VALUE(v.inversion_total), 0)) AS roi_anual
FROM `TU_PROYECTO.finanzas.pnl_mensual` m
JOIN `TU_PROYECTO.finanzas.v_inversion` v USING (propiedad_id)
GROUP BY m.propiedad_id, m.propiedad, m.modelo_negocio, m.moneda, m.anio;

-- =====================================================================
-- OPERACIONES (19-nov-2026)
-- =====================================================================

-- Indicadores operativos por propiedad y mes
CREATE OR REPLACE VIEW `TU_PROYECTO.finanzas.operaciones_mensual` AS
WITH mant AS (
  SELECT
    propiedad_id,
    DATE_TRUNC(fecha_reporte, MONTH)                                   AS mes,
    COUNT(*)                                                           AS mantenimientos,
    COUNTIF(LOWER(prioridad) = 'urgente')                              AS urgentes,
    COUNTIF(LOWER(tipo) = 'correctiva')                                AS correctivos,
    COUNTIF(LOWER(tipo) = 'preventiva')                                AS preventivos,
    COUNTIF(LOWER(tipo) LIKE 'da%o de hu%sped')                        AS danos_huesped,
    COUNTIF(cobrable_huesped)                                          AS cobrables_huesped,
    COUNTIF(LOWER(estado) IN ('pendiente', 'en curso'))                AS abiertos,
    SUM(IFNULL(noches_bloqueadas, 0))                                  AS noches_bloqueadas,
    AVG(dias_resolver)                                                 AS dias_promedio_resolver
  FROM `TU_PROYECTO.finanzas.mantenimientos`
  WHERE fecha_reporte IS NOT NULL
  GROUP BY 1, 2
),
aseos AS (
  SELECT propiedad_id, DATE_TRUNC(fecha, MONTH) AS mes, COUNT(*) AS aseos_programados
  FROM `TU_PROYECTO.finanzas.limpiezas`
  GROUP BY 1, 2
),
gastos AS (
  SELECT propiedad_id, mes,
    SUM(IF(grupo = 'MANTENIMIENTO', monto, 0)) AS gasto_mantenimiento,
    SUM(IF(categoria = 'limpieza', monto, 0))  AS gasto_limpieza,
    SUM(IF(categoria IN ('amenities', 'lavanderia'), monto, 0)) AS gasto_insumos_lavanderia
  FROM `TU_PROYECTO.finanzas.v_movimientos`
  WHERE tipo = 'GASTO'
  GROUP BY 1, 2
)
SELECT
  COALESCE(m.propiedad_id, a.propiedad_id, g.propiedad_id) AS propiedad_id,
  COALESCE(m.mes, a.mes, g.mes)                            AS mes,
  IFNULL(m.mantenimientos, 0) AS mantenimientos, IFNULL(m.urgentes, 0) AS urgentes,
  IFNULL(m.correctivos, 0) AS correctivos, IFNULL(m.preventivos, 0) AS preventivos,
  IFNULL(m.danos_huesped, 0) AS danos_huesped, IFNULL(m.cobrables_huesped, 0) AS cobrables_huesped,
  IFNULL(m.abiertos, 0) AS abiertos, IFNULL(m.noches_bloqueadas, 0) AS noches_bloqueadas,
  m.dias_promedio_resolver,
  IFNULL(a.aseos_programados, 0) AS aseos_programados,
  IFNULL(g.gasto_mantenimiento, 0) AS gasto_mantenimiento,
  IFNULL(g.gasto_limpieza, 0) AS gasto_limpieza,
  IFNULL(g.gasto_insumos_lavanderia, 0) AS gasto_insumos_lavanderia
FROM mant m
FULL OUTER JOIN aseos a USING (propiedad_id, mes)
FULL OUTER JOIN gastos g USING (propiedad_id, mes);

-- Alertas vigentes: preventivas vencidas o sin registro, stock bajo, inventario a reparar, mantenimientos abiertos
CREATE OR REPLACE VIEW `TU_PROYECTO.finanzas.alertas_operacion` AS
SELECT 'PREVENTIVA' AS tipo, propiedad_id, tarea AS detalle, estado,
       proxima_fecha AS fecha
FROM `TU_PROYECTO.finanzas.preventivas`
WHERE UPPER(estado) IN ('VENCIDA', 'PRÓXIMA', 'PROXIMA') OR proxima_fecha < CURRENT_DATE()
UNION ALL
SELECT 'STOCK', NULL, CONCAT(item, ' (', IFNULL(ubicacion, ''), '): ', CAST(cantidad AS STRING), ' de mínimo ', CAST(stock_minimo AS STRING)), estado, NULL
FROM `TU_PROYECTO.finanzas.stock`
WHERE UPPER(estado) = 'COMPRAR' OR (stock_minimo IS NOT NULL AND cantidad <= stock_minimo)
UNION ALL
SELECT 'INVENTARIO', propiedad_id, CONCAT(item, IFNULL(CONCAT(' — ', detalle), '')), estado, NULL
FROM `TU_PROYECTO.finanzas.inventario`
WHERE LOWER(estado) IN ('a reparar', 'reparar', 'a reponer', 'reponer', 'faltante', 'malo')
UNION ALL
SELECT 'MANTENCION_ABIERTA', propiedad_id, CONCAT(IFNULL(prioridad, ''), ': ', IFNULL(descripcion, '')), estado, fecha_reporte
FROM `TU_PROYECTO.finanzas.mantenimientos`
WHERE LOWER(estado) IN ('pendiente', 'en curso');

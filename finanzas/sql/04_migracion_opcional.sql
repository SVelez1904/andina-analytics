-- =====================================================================
-- 04_migracion_opcional.sql — Traer reservas históricas que ya tienes en BigQuery
-- PLANTILLA: cambia `TU_DATASET_ACTUAL.reservas` y los nombres de columnas por los de tu tabla
-- (la que cargas desde los Excel de Stays). Ejecútala UNA sola vez.
-- Primero corre solo el SELECT para revisar; después descomenta el INSERT.
-- =====================================================================

-- INSERT INTO `TU_PROYECTO.finanzas.movimientos`
--   (movimiento_id, fecha, propiedad_id, tipo, categoria, monto, moneda, descripcion,
--    referencia, noches, fuente, estado, clasificado_por, creado_por, creado_en)
SELECT
  TO_HEX(SHA1(CONCAT('MIGRACION|', r.codigo_reserva)))   AS movimiento_id,
  DATE(r.fecha_checkin)                                  AS fecha,
  map.propiedad_id                                       AS propiedad_id,
  'INGRESO'                                              AS tipo,
  'reserva_airbnb'                                       AS categoria,
  CAST(r.ingreso_bruto AS NUMERIC)                       AS monto,
  r.moneda                                               AS moneda,
  CONCAT('Reserva migrada ', r.codigo_reserva)           AS descripcion,
  r.codigo_reserva                                       AS referencia,
  r.noches                                               AS noches,
  'MIGRACION'                                            AS fuente,
  IF(map.propiedad_id IS NULL, 'PENDIENTE', 'OK')        AS estado,
  'MIGRACION'                                            AS clasificado_por,
  'migracion'                                            AS creado_por,
  CURRENT_TIMESTAMP()                                    AS creado_en
FROM `TU_PROYECTO.TU_DATASET_ACTUAL.reservas` r
LEFT JOIN `TU_PROYECTO.finanzas.propiedades` map
  ON map.anuncio_airbnb = r.nombre_anuncio      -- o el campo que identifique la propiedad
WHERE r.estado_reserva NOT IN ('cancelada', 'canceled');

-- Si también tienes la comisión de Airbnb por reserva, repite el bloque con:
--   tipo = 'GASTO', categoria = 'comision_airbnb', monto = r.comision_airbnb,
--   y en movimiento_id usa CONCAT('MIGRACION-COM|', r.codigo_reserva).

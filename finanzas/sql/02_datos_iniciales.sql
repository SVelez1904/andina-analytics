-- =====================================================================
-- 02_datos_iniciales.sql — Categorías, propiedades, usuarios y reglas de ejemplo
-- Edita los valores de propiedades / usuarios / reglas antes de ejecutar.
-- =====================================================================

-- Categorías (puedes agregar más después; no borres las que ya tengan movimientos)
INSERT INTO `TU_PROYECTO.finanzas.categorias` (categoria, tipo, grupo, descripcion) VALUES
  ('reserva_airbnb',          'INGRESO', 'INGRESO',       'Ingreso bruto de reservas Airbnb (incluye tarifa de limpieza cobrada)'),
  ('comision_cohost',         'INGRESO', 'INGRESO',       'Comisión que cobras como co-anfitriona'),
  ('ajuste_airbnb',           'INGRESO', 'INGRESO',       'Ajustes y pagos de resolución de Airbnb a favor'),
  ('otro_ingreso',            'INGRESO', 'INGRESO',       'Otros ingresos'),
  ('comision_airbnb',         'GASTO',   'COMISION',      'Tarifa de servicio que cobra Airbnb al anfitrión'),
  ('ajuste_airbnb_cargo',     'GASTO',   'COMISION',      'Ajustes de Airbnb en contra (reembolsos, penalidades)'),
  ('limpieza',                'GASTO',   'OPERATIVO',     'Pago a personal de limpieza'),
  ('lavanderia',              'GASTO',   'OPERATIVO',     'Lavandería de ropa de cama y toallas'),
  ('amenities',               'GASTO',   'OPERATIVO',     'Insumos para huéspedes (papel, jabón, café, etc.)'),
  ('servicios_basicos',       'GASTO',   'OPERATIVO',     'Luz, agua, gas'),
  ('internet_tv',             'GASTO',   'OPERATIVO',     'Internet y TV'),
  ('gastos_comunes',          'GASTO',   'OPERATIVO',     'Gastos comunes / condominio'),
  ('software',                'GASTO',   'OPERATIVO',     'PriceLabs, cerraduras, otras suscripciones'),
  ('mantenimiento',           'GASTO',   'MANTENIMIENTO', 'Mantención preventiva'),
  ('reparaciones',            'GASTO',   'MANTENIMIENTO', 'Reparaciones por daño o falla'),
  ('reposicion',              'GASTO',   'MANTENIMIENTO', 'Reposición de menaje, ropa de cama, equipamiento'),
  ('arriendo',                'GASTO',   'FIJO',          'Arriendo pagado al dueño (arbitraje)'),
  ('contribuciones_seguros',  'GASTO',   'FIJO',          'Contribuciones, seguros'),
  ('contabilidad',            'GASTO',   'FIJO',          'Contador, trámites'),
  ('impuestos',               'GASTO',   'IMPUESTO',      'Impuestos pagados'),
  ('otros_gastos',            'GASTO',   'OPERATIVO',     'Otros gastos operativos'),
  ('liquidacion_propietario', 'GASTO',   'PROPIETARIO',   'Lo que transfieres al dueño cuando el pago de Airbnb entra a tu cuenta');

-- Propiedades: tus 12 unidades (de las planillas de operaciones) + GENERAL.
-- EDITA: modelo_negocio (PROPIA / ARBITRAJE / COHOST / GESTION), comision_pct, inversion_inicial,
-- arriendo_mensual y anuncio_airbnb (nombre EXACTO del anuncio en el CSV de Airbnb).
INSERT INTO `TU_PROYECTO.finanzas.propiedades`
  (propiedad_id, nombre, ciudad, pais, moneda, modelo_negocio, comision_pct, inversion_inicial, arriendo_mensual, anuncio_airbnb, fecha_inicio, activa)
VALUES
  ('GENERAL',        'Gastos generales del negocio', NULL,           'CL', 'CLP', 'GENERAL',     NULL, NULL, NULL, NULL, NULL, TRUE),
  ('ENCINA-911',     'Encina 911',       'Providencia',  'CL', 'CLP', 'POR_DEFINIR', NULL, NULL, NULL, NULL, NULL, TRUE),
  ('ENCINA-1003',    'Encina 1003',      'Providencia',  'CL', 'CLP', 'POR_DEFINIR', NULL, NULL, NULL, NULL, NULL, TRUE),
  ('ENCINA-1101',    'Encina 1101',      'Providencia',  'CL', 'CLP', 'POR_DEFINIR', NULL, NULL, NULL, NULL, NULL, TRUE),
  ('MARIANO-315',    'Mariano 315',      'Providencia',  'CL', 'CLP', 'POR_DEFINIR', NULL, NULL, NULL, NULL, NULL, TRUE),
  ('MARIANO-917',    'Mariano 917',      'Providencia',  'CL', 'CLP', 'POR_DEFINIR', NULL, NULL, NULL, NULL, NULL, TRUE),
  ('MARIANO-1015',   'Mariano 1015',     'Providencia',  'CL', 'CLP', 'POR_DEFINIR', NULL, NULL, NULL, NULL, NULL, TRUE),
  ('MARIANO-1617',   'Mariano 1617',     'Providencia',  'CL', 'CLP', 'POR_DEFINIR', NULL, NULL, NULL, NULL, NULL, TRUE),
  ('STA-ISABEL-157', 'Santa Isabel 157', 'Santiago',     'CL', 'CLP', 'POR_DEFINIR', NULL, NULL, NULL, NULL, NULL, TRUE),
  ('STA-ISABEL-310', 'Santa Isabel 310', 'Santiago',     'CL', 'CLP', 'POR_DEFINIR', NULL, NULL, NULL, NULL, NULL, TRUE),
  ('BOHO-509',       'Boho 509',         'Providencia',  'CL', 'CLP', 'POR_DEFINIR', NULL, NULL, NULL, NULL, NULL, TRUE),
  ('PUCON-403',      'Pucón 403',        'Pucón',        'CL', 'CLP', 'COHOST',      NULL, NULL, NULL, NULL, NULL, TRUE),
  ('CASA-PORTO',     'Casa Porto Seguro','Porto Seguro', 'BR', 'BRL', 'COHOST',      NULL, NULL, NULL, NULL, NULL, TRUE);

-- NUEVO (19-nov): nombres con que aparece cada propiedad en las planillas de operaciones.
-- "General", "Varios deptos", "Oficina", "Bodegas" y "Leticia / Admin" van solos a GENERAL (no hace falta listarlos).
INSERT INTO `TU_PROYECTO.finanzas.alias_propiedades` (alias, propiedad_id) VALUES
  ('Encina 911', 'ENCINA-911'), ('Encina 1003', 'ENCINA-1003'), ('Encina 1101', 'ENCINA-1101'),
  ('Mariano 315', 'MARIANO-315'), ('Mariano 917', 'MARIANO-917'), ('Mariano 1015', 'MARIANO-1015'),
  ('Mariano 1617', 'MARIANO-1617'), ('Pucón 403', 'PUCON-403'), ('Boho 509', 'BOHO-509'),
  ('Casa Porto', 'CASA-PORTO'), ('Santa Isabel 157', 'STA-ISABEL-157'), ('Sta Isabel 157', 'STA-ISABEL-157'),
  ('Santa Isabel 310', 'STA-ISABEL-310'), ('Sta Isabel 310', 'STA-ISABEL-310');

-- NUEVO (19-nov): equipo de limpieza (de la hoja "limpeza meninas"). Si una persona atiende varias
-- propiedades, su pago del mes se reparte según las reservas de cada una.
INSERT INTO `TU_PROYECTO.finanzas.equipo_limpieza` (nombre, propiedades, tarifa_aseo, activa) VALUES
  ('Javiera',  ['PUCON-403'], 30000, TRUE),
  ('Angelica', ['BOHO-509'],  20000, TRUE),
  ('Bexi',     ['ENCINA-911', 'ENCINA-1003', 'ENCINA-1101', 'MARIANO-315', 'MARIANO-917', 'MARIANO-1015', 'MARIANO-1617'], 30000, TRUE);

-- NUEVO (19-nov): presupuesto de reforma de Boho 509 (493.850 CLP con IVA). Cambia estado a EJECUTADO
-- cuando se haga el trabajo: recién ahí suma a la inversión y al ROI.
INSERT INTO `TU_PROYECTO.finanzas.inversiones`
  (inversion_id, fecha, propiedad_id, concepto, tipo, monto_neto, monto_total, moneda, estado, carga_id, creado_en)
VALUES
  ('BOHO-509-PINTURA-2026', CURRENT_DATE(), 'BOHO-509', 'Pintura muros, terraza y cielo baño', 'REFORMA', 415000, 493850, 'CLP', 'PRESUPUESTO', 'manual', CURRENT_TIMESTAMP());

-- Usuarios de la app (además, cada email debe tener acceso en IAP; ver guía, Paso 5)
INSERT INTO `TU_PROYECTO.finanzas.usuarios` (email, nombre, rol, propiedades) VALUES
  ('tu-email@gmail.com',    'Leticia', 'ADMIN',    []),
  ('email-de-tu-jefa@...',  'Jefa',    'ADMIN',    []);
  -- Ejemplo de propietario que solo ve lo suyo:
  -- ('dueno@gmail.com', 'Dueño Porto Seguro', 'PROPIETARIO', ['PORTO-SEGURO']);

-- Reglas iniciales (ajusta los textos a cómo aparecen en TU cartola)
INSERT INTO `TU_PROYECTO.finanzas.reglas_clasificacion` (patron, categoria, propiedad_id, prioridad, creado_en) VALUES
  ('PRICELABS', 'software',          'GENERAL', 10, CURRENT_TIMESTAMP()),
  ('ENEL',      'servicios_basicos', NULL,      20, CURRENT_TIMESTAMP()),
  ('AGUAS ',    'servicios_basicos', NULL,      20, CURRENT_TIMESTAMP()),
  ('METROGAS',  'servicios_basicos', NULL,      20, CURRENT_TIMESTAMP()),
  ('LIPIGAS',   'servicios_basicos', NULL,      20, CURRENT_TIMESTAMP()),
  ('SODIMAC',   'mantenimiento',     NULL,      30, CURRENT_TIMESTAMP()),
  ('EASY',      'mantenimiento',     NULL,      30, CURRENT_TIMESTAMP());

-- Las transferencias del banco a la caja chica y a las personas de limpieza YA están en las planillas
-- de operaciones: se marcan como DESCARTADO para no contarlas dos veces. Ajusta los textos a tu cartola.
-- INSERT INTO `TU_PROYECTO.finanzas.reglas_clasificacion` (patron, categoria, propiedad_id, prioridad, creado_en) VALUES
--   ('TRANSF A CAJA CHICA', '__DESCARTAR__', NULL, 1, CURRENT_TIMESTAMP()),
--   ('TRANSF BEXI',         '__DESCARTAR__', NULL, 1, CURRENT_TIMESTAMP());

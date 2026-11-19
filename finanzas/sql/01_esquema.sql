-- =====================================================================
-- 01_esquema.sql — Dataset y tablas del sistema de finanzas por propiedad
-- Ejecutar en la consola de BigQuery (o con: bq query --use_legacy_sql=false < 01_esquema.sql)
-- Reemplaza TU_PROYECTO por el ID de tu proyecto de GCP antes de ejecutar.
-- Requiere facturación activa (el modo Sandbox no permite INSERT/UPDATE y borra tablas a los 60 días).
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS `TU_PROYECTO.finanzas`
OPTIONS (location = 'US', description = 'Finanzas por propiedad (STR)');

-- ---------------------------------------------------------------------
-- 1) Propiedades: una fila por propiedad + una fila GENERAL para gastos del negocio
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.propiedades` (
  propiedad_id        STRING  NOT NULL OPTIONS (description = 'Código corto, ej. PUCON-PAYLLAHUE'),
  nombre              STRING  NOT NULL,
  ciudad              STRING,
  pais                STRING  OPTIONS (description = 'CL / BR'),
  moneda              STRING  NOT NULL OPTIONS (description = 'CLP / BRL'),
  modelo_negocio      STRING  NOT NULL OPTIONS (description = 'PROPIA / ARBITRAJE / COHOST / GESTION / GENERAL'),
  comision_pct        NUMERIC OPTIONS (description = 'Solo COHOST/GESTION: % que cobras, ej. 0.20'),
  inversion_inicial   NUMERIC OPTIONS (description = 'Lo que invertiste (amoblado, garantía, habilitación). Base del ROI'),
  arriendo_mensual    NUMERIC OPTIONS (description = 'Solo ARBITRAJE: arriendo que pagas'),
  anuncio_airbnb      STRING  OPTIONS (description = 'Nombre EXACTO del anuncio como aparece en el CSV de Airbnb'),
  fecha_inicio        DATE,
  activa              BOOL    NOT NULL
);

-- ---------------------------------------------------------------------
-- 2) Categorías: lista cerrada para que la IA y las personas clasifiquen igual
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.categorias` (
  categoria   STRING NOT NULL,
  tipo        STRING NOT NULL OPTIONS (description = 'INGRESO / GASTO'),
  grupo       STRING NOT NULL OPTIONS (description = 'INGRESO / COMISION / OPERATIVO / MANTENIMIENTO / FIJO / IMPUESTO / PROPIETARIO'),
  descripcion STRING
);

-- ---------------------------------------------------------------------
-- 3) Movimientos: TODOS los ingresos y gastos, en su moneda original
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.movimientos` (
  movimiento_id    STRING    NOT NULL OPTIONS (description = 'Hash único: evita duplicados al subir el mismo archivo dos veces'),
  fecha            DATE      NOT NULL OPTIONS (description = 'Reservas: fecha de check-in. Gastos: fecha del cargo'),
  propiedad_id     STRING             OPTIONS (description = 'NULL = aún no asignado (queda PENDIENTE)'),
  tipo             STRING    NOT NULL OPTIONS (description = 'INGRESO / GASTO'),
  categoria        STRING,
  monto            NUMERIC   NOT NULL OPTIONS (description = 'Siempre positivo; el signo lo da el tipo'),
  moneda           STRING    NOT NULL,
  descripcion      STRING,
  referencia       STRING             OPTIONS (description = 'Código de confirmación Airbnb, N° boleta, etc.'),
  noches           INT64              OPTIONS (description = 'Solo reservas'),
  fuente           STRING    NOT NULL OPTIONS (description = 'AIRBNB_CSV / BANCO / BOLETA / MANUAL / MIGRACION'),
  estado           STRING    NOT NULL OPTIONS (description = 'OK / PENDIENTE / DESCARTADO'),
  clasificado_por  STRING             OPTIONS (description = 'AIRBNB / REGLA / IA / HUMANO'),
  confianza        FLOAT64,
  sugerencia       STRING             OPTIONS (description = 'Sugerencia de la IA cuando quedó pendiente'),
  archivo_url      STRING             OPTIONS (description = 'Foto de la boleta en Cloud Storage'),
  carga_id         STRING,
  creado_por       STRING,
  creado_en        TIMESTAMP NOT NULL
)
PARTITION BY DATE_TRUNC(fecha, MONTH)
CLUSTER BY propiedad_id, estado;

-- ---------------------------------------------------------------------
-- 4) Reglas de clasificación: "si la descripción contiene X → categoría Y (y propiedad Z)"
--    Se aplican antes que la IA. La pantalla Pendientes puede crear reglas nuevas.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.reglas_clasificacion` (
  patron        STRING NOT NULL OPTIONS (description = 'Texto a buscar en la descripción (sin distinguir mayúsculas)'),
  categoria     STRING NOT NULL,
  propiedad_id  STRING          OPTIONS (description = 'NULL = la regla no decide la propiedad'),
  prioridad     INT64  NOT NULL OPTIONS (description = 'Menor número = se evalúa primero'),
  creado_en     TIMESTAMP
);

-- ---------------------------------------------------------------------
-- 5) Usuarios y permisos de la app
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.usuarios` (
  email         STRING NOT NULL,
  nombre        STRING,
  rol           STRING NOT NULL OPTIONS (description = 'ADMIN / OPERADOR / PROPIETARIO'),
  propiedades   ARRAY<STRING>   OPTIONS (description = 'Solo PROPIETARIO: propiedades que puede ver')
);

-- ---------------------------------------------------------------------
-- 6) Registro de cargas (auditoría)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.cargas` (
  carga_id      STRING NOT NULL,
  fuente        STRING,
  archivo       STRING,
  filas_leidas  INT64,
  filas_nuevas  INT64,
  pendientes    INT64,
  usuario       STRING,
  creado_en     TIMESTAMP
);

-- =====================================================================
-- OPERACIONES (agregado 19-nov-2026): planillas de la carpeta 3. OPERATIONS
-- Todo es CREATE ... IF NOT EXISTS: puedes volver a ejecutar este archivo sin perder datos.
-- =====================================================================

-- 7) Nombres con que aparece cada propiedad en las planillas ("Encina 911", "ENCINA 911", "Pucón 403"...)
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.alias_propiedades` (
  alias         STRING NOT NULL OPTIONS (description = 'Se compara sin mayúsculas, tildes ni espacios extra'),
  propiedad_id  STRING NOT NULL
);

-- 8) Equipo de limpieza: qué propiedades atiende cada persona (para repartir su pago mensual)
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.equipo_limpieza` (
  nombre          STRING NOT NULL OPTIONS (description = 'Primer nombre, como aparece en la hoja "limpeza meninas"'),
  propiedades     ARRAY<STRING>,
  tarifa_aseo     NUMERIC,
  activa          BOOL
);

-- 9) Registro de mantenimientos (fotografía de la hoja "Registro"; se reemplaza en cada carga)
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.mantenimientos` (
  mantenimiento_id   STRING NOT NULL,
  fecha_reporte      DATE,
  propiedad_id       STRING,
  propiedad_planilla STRING,
  ambiente           STRING,
  categoria          STRING,
  item               STRING,
  descripcion        STRING,
  tipo               STRING OPTIONS (description = 'Correctiva / Preventiva / Mejora / Daño de huésped'),
  prioridad          STRING,
  origen             STRING,
  realizado_por      STRING,
  fecha_ejecucion    DATE,
  estado             STRING,
  dias_resolver      FLOAT64,
  costo_registrado   FLOAT64 OPTIONS (description = 'Informativo. El dinero se toma de la planilla de gastos para no contar dos veces'),
  bloqueo_reservas   BOOL,
  noches_bloqueadas  FLOAT64,
  cobrable_huesped   BOOL,
  codigo_reserva     STRING,
  carga_id           STRING,
  actualizado_en     TIMESTAMP
);

-- 10) Plan preventivo (fotografía de la hoja "Preventivas")
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.preventivas` (
  propiedad_id       STRING,
  propiedad_planilla STRING,
  tarea              STRING,
  categoria          STRING,
  frecuencia_dias    FLOAT64,
  ultima_ejecucion   DATE,
  proxima_fecha      DATE,
  estado             STRING,
  responsable        STRING,
  carga_id           STRING,
  actualizado_en     TIMESTAMP
);

-- 11) Aseos programados (de la hoja de turnos semanales; se acumulan semana a semana)
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.limpiezas` (
  limpieza_id        STRING NOT NULL,
  fecha              DATE,
  propiedad_id       STRING,
  propiedad_planilla STRING,
  carga_id           STRING,
  creado_en          TIMESTAMP
);

-- 12) Inventario por departamento (fotografía)
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.inventario` (
  propiedad_id       STRING,
  propiedad_planilla STRING,
  ambiente           STRING,
  categoria          STRING,
  item               STRING,
  detalle            STRING,
  cantidad           FLOAT64,
  valor_unitario     FLOAT64,
  valor_total        FLOAT64,
  estado             STRING,
  fecha_compra       DATE,
  carga_id           STRING,
  actualizado_en     TIMESTAMP
);

-- 13) Stock de bodega: ropa de cama y baño, amenities, limpieza (fotografía)
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.stock` (
  tipo_stock      STRING OPTIONS (description = 'ROPA_CAMA_BANO / AMENITIES / LIMPIEZA'),
  ubicacion       STRING,
  item            STRING,
  cantidad        FLOAT64,
  stock_minimo    FLOAT64,
  estado          STRING,
  danadas         FLOAT64,
  carga_id        STRING,
  actualizado_en  TIMESTAMP
);

-- 14) Inversiones (reformas, amoblado). Solo las EJECUTADAS suman al ROI.
CREATE TABLE IF NOT EXISTS `TU_PROYECTO.finanzas.inversiones` (
  inversion_id  STRING NOT NULL,
  fecha         DATE,
  propiedad_id  STRING,
  concepto      STRING,
  tipo          STRING OPTIONS (description = 'REFORMA / AMOBLADO / EQUIPAMIENTO / GARANTIA'),
  monto_neto    NUMERIC,
  monto_total   NUMERIC,
  moneda        STRING,
  estado        STRING OPTIONS (description = 'PRESUPUESTO / EJECUTADO / DESCARTADO'),
  carga_id      STRING,
  creado_en     TIMESTAMP
);

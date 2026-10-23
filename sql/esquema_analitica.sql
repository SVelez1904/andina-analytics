-- =============================================================================
-- Esquema "analitica" y usuario de análisis (andina_analytics)
--
-- Ejecutar UNA vez (y de nuevo si cambia este archivo), con el usuario dueño de la base
-- (el mismo que usa andina_lab, ej. "stays"), desde la carpeta andina_analytics:
--
--   psql -h localhost -U stays -d stays -v analitica_pass='UNA-CLAVE-SEGURA' -f sql/esquema_analitica.sql
--
-- Qué hace:
--   - Crea el usuario analitica_app: LEE el esquema public (tablas y vistas de andina_lab)
--     y ESCRIBE solo en el esquema analitica. No puede modificar tus datos del negocio.
--   - Le quita acceso a lo sensible: huéspedes, usuarios de Django y la vista con nombres.
--   - Crea las tablas y vistas de análisis (temas de reviews, pronósticos, reportes).
-- Es idempotente: se puede volver a ejecutar sin perder datos.
-- =============================================================================

\set ON_ERROR_STOP on

-- 1. Usuario de análisis ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analitica_app') THEN
        CREATE ROLE analitica_app LOGIN;
    END IF;
END $$;
ALTER ROLE analitica_app PASSWORD :'analitica_pass';

DO $$ BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO analitica_app', current_database());
END $$;

-- 2. Lectura del esquema public (lo que mantiene andina_lab) ---------------------------
GRANT USAGE ON SCHEMA public TO analitica_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analitica_app;      -- incluye las vistas
-- Las vistas que andina_lab vuelva a crear también quedarán legibles:
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analitica_app;

-- Nada de datos personales ni credenciales
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['dim_hospedes', 'vw_reservas_analisis', 'auth_user', 'auth_user_groups',
                             'auth_user_user_permissions', 'django_session', 'django_admin_log']
    LOOP
        IF to_regclass('public.' || t) IS NOT NULL THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM analitica_app', t);
        END IF;
    END LOOP;
END $$;

-- 3. Esquema propio ---------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS analitica;
GRANT USAGE ON SCHEMA analitica TO analitica_app;

-- Temas de reviews clasificados con IA
CREATE TABLE IF NOT EXISTS analitica.review_temas (
    id               bigserial PRIMARY KEY,
    id_avaliacion    integer NOT NULL REFERENCES public.avaliaciones (id_avaliacion) ON DELETE CASCADE,
    tema             varchar(30) NOT NULL,
    sentimiento      varchar(10) NOT NULL CHECK (sentimiento IN ('positivo', 'negativo', 'neutro')),
    severidad        smallint CHECK (severidad BETWEEN 1 AND 3),
    cita             text,
    fuente           varchar(10) CHECK (fuente IN ('publico', 'privado')),
    accion_sugerida  text,
    modelo_ia        varchar(60),
    clasificado      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS review_temas_avaliacion_idx ON analitica.review_temas (id_avaliacion);

-- Pronóstico por propiedad y mes (una "foto" por fecha de corte)
CREATE TABLE IF NOT EXISTS analitica.pronostico_ocupacion (
    fecha_corte        date        NOT NULL,
    id_propriedade     varchar(64) NOT NULL,
    mes                date        NOT NULL,
    disponibles        integer,
    reservadas_ya      integer,
    noches_pronostico  numeric(8, 2),
    ingreso_ya         numeric(14, 2),
    ingreso_pronostico numeric(14, 2),
    moneda             varchar(3),
    factor_propiedad   numeric(6, 3),
    generado           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (fecha_corte, id_propriedade, mes)
);

-- Pronóstico noche a noche (para "noches en riesgo")
CREATE TABLE IF NOT EXISTS analitica.pronostico_noches (
    fecha_corte     date        NOT NULL,
    id_propriedade  varchar(64) NOT NULL,
    fecha           date        NOT NULL,
    reservada       boolean     NOT NULL,
    probabilidad    numeric(5, 4) NOT NULL,
    PRIMARY KEY (fecha_corte, id_propriedade, fecha)
);

-- Reportes generados
CREATE TABLE IF NOT EXISTS analitica.reportes (
    id              bigserial PRIMARY KEY,
    generado        timestamptz NOT NULL DEFAULT now(),
    fecha_corte     date NOT NULL,
    titulo          text,
    contenido_md    text,
    datos           jsonb,
    modelo_ia       varchar(60),
    tokens_entrada  integer,
    tokens_salida   integer,
    archivo         text
);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA analitica TO analitica_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA analitica TO analitica_app;

-- 4. Vistas de análisis -----------------------------------------------------------------
DROP VIEW IF EXISTS analitica.vw_finanzas_reservas;
DROP VIEW IF EXISTS analitica.vw_noches_en_riesgo;
DROP VIEW IF EXISTS analitica.vw_pronostico_actual;
DROP VIEW IF EXISTS analitica.vw_fortalezas_propiedad;
DROP VIEW IF EXISTS analitica.vw_pendientes_propiedad;
DROP VIEW IF EXISTS analitica.vw_temas_mensual;
DROP VIEW IF EXISTS analitica.vw_review_temas_detalle;

CREATE VIEW analitica.vw_review_temas_detalle AS
SELECT t.id, t.id_avaliacion, a.fecha, date_trunc('month', a.fecha)::date AS mes,
       a.id_propriedade, p.nome_anuncio AS propiedad, a.rating_general,
       t.tema, t.sentimiento, t.severidad, t.cita, t.fuente, t.accion_sugerida, t.modelo_ia
FROM analitica.review_temas t
JOIN public.avaliaciones a        ON a.id_avaliacion = t.id_avaliacion
LEFT JOIN public.dim_propiedades p ON p.id_interno = a.id_propriedade
WHERE NOT (t.tema = 'otro' AND t.cita = '(elogio general, sin temas concretos)');

CREATE VIEW analitica.vw_temas_mensual AS
SELECT id_propriedade, propiedad, mes, tema,
       COUNT(*) FILTER (WHERE sentimiento = 'positivo') AS positivos,
       COUNT(*) FILTER (WHERE sentimiento = 'negativo') AS negativos,
       COUNT(*) FILTER (WHERE sentimiento = 'neutro')   AS sugerencias,
       MAX(severidad)                                   AS severidad_maxima
FROM analitica.vw_review_temas_detalle
GROUP BY id_propriedade, propiedad, mes, tema;

-- Lo que hay que corregir en cada propiedad (últimos 90 días). Prioridad = suma de severidades.
CREATE VIEW analitica.vw_pendientes_propiedad AS
SELECT id_propriedade, propiedad, tema,
       COUNT(*)                                       AS menciones,
       COUNT(DISTINCT id_avaliacion)                  AS reviews,
       SUM(COALESCE(severidad, 1))                    AS prioridad,
       MAX(severidad)                                 AS severidad_maxima,
       MAX(fecha)                                     AS ultima_mencion,
       COUNT(*) FILTER (WHERE fuente = 'privado')     AS en_comentario_privado,
       (ARRAY_AGG(cita ORDER BY severidad DESC NULLS LAST, fecha DESC))[1:3] AS citas,
       ARRAY_AGG(DISTINCT accion_sugerida) FILTER (WHERE accion_sugerida IS NOT NULL) AS acciones_sugeridas
FROM analitica.vw_review_temas_detalle
WHERE sentimiento IN ('negativo', 'neutro') AND tema <> 'externo' AND fecha >= CURRENT_DATE - 90
GROUP BY id_propriedade, propiedad, tema;

CREATE VIEW analitica.vw_fortalezas_propiedad AS
SELECT id_propriedade, propiedad, tema, COUNT(*) AS menciones,
       (ARRAY_AGG(cita ORDER BY fecha DESC))[1:3] AS citas
FROM analitica.vw_review_temas_detalle
WHERE sentimiento = 'positivo'
GROUP BY id_propriedade, propiedad, tema;

-- Último pronóstico guardado
CREATE VIEW analitica.vw_pronostico_actual AS
SELECT po.*, p.nome_anuncio AS propiedad,
       po.reservadas_ya::numeric / NULLIF(po.disponibles, 0)     AS ocupacion_ya,
       po.noches_pronostico / NULLIF(po.disponibles, 0)          AS ocupacion_pronostico
FROM analitica.pronostico_ocupacion po
JOIN public.dim_propiedades p ON p.id_interno = po.id_propriedade
WHERE po.fecha_corte = (SELECT MAX(fecha_corte) FROM analitica.pronostico_ocupacion);

-- Noches libres de los próximos 21 días, de la menos a la más probable de venderse
CREATE VIEW analitica.vw_noches_en_riesgo AS
SELECT pn.fecha_corte, pn.id_propriedade, p.nome_anuncio AS propiedad, pn.fecha,
       pn.fecha - pn.fecha_corte AS dias_para_la_noche,
       to_char(pn.fecha, 'TMDy') AS dia_semana,
       pn.probabilidad
FROM analitica.pronostico_noches pn
JOIN public.dim_propiedades p ON p.id_interno = pn.id_propriedade
WHERE pn.fecha_corte = (SELECT MAX(fecha_corte) FROM analitica.pronostico_noches)
  AND NOT pn.reservada
  AND pn.fecha BETWEEN pn.fecha_corte AND pn.fecha_corte + 20;   -- 21 noches, incluida la de hoy

-- Desglose del KPI de ingresos: una fila por reserva y mes. ingreso_mes_clp suma exactamente lo mismo
-- que SUM(ingreso_noche_clp) de public.vw_fct_noches (página Finanzas). Las canceladas van con
-- considerada = FALSE e ingreso 0, solo para mostrar qué quedó fuera. Sin datos del huésped.
CREATE VIEW analitica.vw_finanzas_reservas AS
WITH noches AS (                 -- lo que suma el KPI de ingresos: noches vendidas de vw_fct_noches
    SELECT n.id_reserva,
           date_trunc('month', n.fecha)::date                    AS mes,
           MIN(n.moneda_local)                                   AS moneda_local,
           COUNT(*)                                              AS noches_mes,
           SUM(n.ingreso_noche_original)                         AS ingreso_mes_original,
           SUM(n.ingreso_noche_clp)                              AS ingreso_mes_clp,
           COUNT(*) FILTER (WHERE n.ingreso_noche_clp IS NULL)   AS noches_sin_tipo_cambio
    FROM public.vw_fct_noches n
    WHERE n.vendida
    GROUP BY n.id_reserva, date_trunc('month', n.fecha)
),
canceladas AS (                  -- no suman: se muestran para saber qué quedó fuera
    SELECT r.id_reserva,
           date_trunc('month', r.data_chegada + d)::date         AS mes,
           COUNT(*)                                              AS noches_mes
    FROM public.reservas r
    CROSS JOIN LATERAL generate_series(0, GREATEST(r.data_checkout - r.data_chegada, 1) - 1) AS d
    WHERE r.data_cancelamento IS NOT NULL OR LOWER(r.status_reserva) LIKE '%cancel%'
    GROUP BY r.id_reserva, date_trunc('month', r.data_chegada + d)
),
filas AS (
    SELECT id_reserva, mes, moneda_local, noches_mes, ingreso_mes_original, ingreso_mes_clp,
           noches_sin_tipo_cambio, TRUE AS considerada
    FROM noches
    UNION ALL
    SELECT id_reserva, mes, NULL, noches_mes, 0, 0, 0, FALSE
    FROM canceladas
)
SELECT f.mes,
       f.considerada,
       r.id_reserva,
       r.numero_registro,
       p.nome_anuncio                                            AS propiedad,
       CASE COALESCE(f.moneda_local, pf.moneda_local, 'CLP') WHEN 'BRL' THEN 'Brasil' ELSE 'Chile' END AS mercado,
       ca.nome_canal                                             AS canal,
       r.status_reserva,
       r.data_criacao                                            AS fecha_reserva,
       r.data_chegada                                            AS llegada,
       r.data_checkout                                           AS salida,
       r.data_cancelamento                                       AS fecha_cancelacion,
       GREATEST(r.data_checkout - r.data_chegada, 1)             AS noches_reserva,
       f.noches_mes,
       r.moeda                                                   AS moneda,
       r.total_reserva,
       COALESCE(r.taxa_limpeza, 0)                               AS limpieza,
       r.total_reserva - COALESCE(r.taxa_limpeza, 0)             AS ingreso_alojamiento,
       r.comissao_empresa                                        AS comision,
       f.ingreso_mes_original,
       f.ingreso_mes_clp,
       f.noches_sin_tipo_cambio
FROM filas f
JOIN public.reservas r              ON r.id_reserva = f.id_reserva
JOIN public.dim_propiedades p       ON p.id_interno = r.id_propriedade
LEFT JOIN public.propiedad_fechas pf ON pf.id_propriedade = r.id_propriedade
LEFT JOIN public.dim_canales ca     ON ca.id_canal = r.id_canal;

GRANT SELECT ON ALL TABLES IN SCHEMA analitica TO analitica_app;

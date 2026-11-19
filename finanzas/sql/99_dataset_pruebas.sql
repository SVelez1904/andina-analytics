-- =====================================================================
-- 99_dataset_pruebas.sql — Crea `finanzas_dev`, una copia para las vistas previas de los PR.
-- Usa CLONE: la copia es instantánea y solo ocupa espacio por lo que cambie (dentro del nivel gratuito).
-- Vuelve a ejecutarlo cuando quieras refrescar la copia con los datos actuales.
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS `TU_PROYECTO.finanzas_dev` OPTIONS (location = 'US');

CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.propiedades`          CLONE `TU_PROYECTO.finanzas.propiedades`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.categorias`           CLONE `TU_PROYECTO.finanzas.categorias`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.movimientos`          CLONE `TU_PROYECTO.finanzas.movimientos`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.reglas_clasificacion` CLONE `TU_PROYECTO.finanzas.reglas_clasificacion`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.usuarios`             CLONE `TU_PROYECTO.finanzas.usuarios`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.cargas`               CLONE `TU_PROYECTO.finanzas.cargas`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.alias_propiedades`    CLONE `TU_PROYECTO.finanzas.alias_propiedades`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.equipo_limpieza`      CLONE `TU_PROYECTO.finanzas.equipo_limpieza`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.mantenimientos`       CLONE `TU_PROYECTO.finanzas.mantenimientos`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.preventivas`          CLONE `TU_PROYECTO.finanzas.preventivas`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.limpiezas`            CLONE `TU_PROYECTO.finanzas.limpiezas`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.inventario`           CLONE `TU_PROYECTO.finanzas.inventario`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.stock`                CLONE `TU_PROYECTO.finanzas.stock`;
CREATE OR REPLACE TABLE `TU_PROYECTO.finanzas_dev.inversiones`          CLONE `TU_PROYECTO.finanzas.inversiones`;

-- Las vistas: ejecuta también 03_vistas.sql reemplazando `finanzas.` por `finanzas_dev.`
-- (el script deploy/04_github_cicd.sh lo hace por ti).

# finanzas-str

Rentabilidad mensual y anual por propiedad (Airbnb + planillas de operaciones) sobre BigQuery,
con app privada en Cloud Run + IAP, un asistente de Claude (Haiku) con funciones fijas de solo lectura,
informe mensual automático y despliegue continuo desde GitHub.

```
sql/          01_esquema → 02_datos_iniciales → 03_vistas → (04_migracion_opcional) · 99_dataset_pruebas
lib/          bq, parsers (Airbnb + cartolas), operaciones (planillas), clasificador, agente, auth, registro
pages/        1 Cargar datos · 2 Registrar gasto · 3 Pendientes · 4 Rentabilidad · 5 Asistente
informe/      informe_mensual.py (Cloud Run Job)
scripts/      importar_operaciones.py (carga masiva) · validar_sql_bigquery.py (dry-run)
deploy/       01_configurar_gcp · 02_desplegar_app · 03_informe_mensual · 04_github_cicd
.github/      ci.yml (pruebas) · deploy.yml (main → producción) · preview.yml (PR → versión de prueba) · dependabot
tests/        parsers, operaciones, agente, SQL, páginas de la app (Streamlit AppTest)
```

## Trabajo diario

```bash
make instalar        # una vez
make test            # pruebas + cobertura, no necesitan GCP
make app             # app local (requiere: gcloud auth application-default login, GCP_PROYECTO, DEV_USER)
git checkout -b mejora-x && git push   # abre un PR → pruebas + vista previa con datos de prueba
# merge a main → pruebas → despliegue automático a producción
```

La guía paso a paso está en el documento "Sistema de finanzas por propiedad — guía de implementación".

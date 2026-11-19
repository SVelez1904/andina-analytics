#!/usr/bin/env bash
# =====================================================================
# 01_configurar_gcp.sh — Se ejecuta UNA vez. Prepara el proyecto de GCP.
# Uso:  bash deploy/01_configurar_gcp.sh
# Antes: gcloud auth login && gcloud config set project TU_PROYECTO
# =====================================================================
set -euo pipefail

PROYECTO="$(gcloud config get-value project)"
REGION="us-central1"
SA_NOMBRE="finanzas-app"
SA="${SA_NOMBRE}@${PROYECTO}.iam.gserviceaccount.com"
BUCKET="${PROYECTO}-boletas"
NUMERO_PROYECTO="$(gcloud projects describe "$PROYECTO" --format='value(projectNumber)')"

echo "Proyecto: $PROYECTO ($NUMERO_PROYECTO)  Región: $REGION"

# 1) Activar APIs (gratis activarlas; solo se cobra el uso sobre el nivel gratuito)
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  bigquery.googleapis.com secretmanager.googleapis.com iap.googleapis.com \
  cloudscheduler.googleapis.com storage.googleapis.com

# 2) Cuenta de servicio con la que corre la app (sin archivo de llaves)
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$SA_NOMBRE" --display-name="App finanzas STR"

# Puede ejecutar consultas en el proyecto (los permisos sobre el dataset se dan con GRANT en BigQuery)
gcloud projects add-iam-policy-binding "$PROYECTO" \
  --member="serviceAccount:$SA" --role="roles/bigquery.jobUser" --condition=None >/dev/null

# 3) Bucket para fotos de boletas (región us-central1 = dentro del nivel gratuito de 5 GB)
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SA" --role="roles/storage.objectCreator" >/dev/null

# 4) Secretos: API key de Claude y contraseña de aplicación de Gmail (para el informe)
crear_secreto () {
  local nombre="$1"; local pregunta="$2"
  if ! gcloud secrets describe "$nombre" >/dev/null 2>&1; then
    read -r -s -p "$pregunta (Enter para omitir): " valor; echo
    if [ -z "$valor" ]; then echo "  $nombre omitido"; return 0; fi
    printf '%s' "$valor" | gcloud secrets create "$nombre" --data-file=- --replication-policy=automatic
  fi
  gcloud secrets add-iam-policy-binding "$nombre" \
    --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor" >/dev/null
}
crear_secreto anthropic-api-key "Pega tu API key de Anthropic (sk-ant-...)"
crear_secreto smtp-password    "Pega la contraseña de aplicación de Gmail (16 letras)"

# 5) Permitir que IAP llame a la app
gcloud beta services identity create --service=iap.googleapis.com --project="$PROYECTO" >/dev/null 2>&1 || true

echo
echo "Listo. Ahora, en la consola de BigQuery ejecuta (reemplazando el proyecto):"
echo "  GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`$PROYECTO.finanzas\` TO \"serviceAccount:$SA\";"
echo "Luego sigue con: bash deploy/02_desplegar_app.sh"

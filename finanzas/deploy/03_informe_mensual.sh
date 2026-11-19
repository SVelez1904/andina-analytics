#!/usr/bin/env bash
# =====================================================================
# 03_informe_mensual.sh — Crea el Job del informe y lo programa para el día 5 de cada mes, 09:00 Chile.
# Uso:  bash deploy/03_informe_mensual.sh "tu-gmail@gmail.com" "tu-email@gmail.com,email-jefa@gmail.com"
#        (1° = cuenta Gmail que envía, 2° = destinatarios)
# =====================================================================
set -euo pipefail

PROYECTO="$(gcloud config get-value project)"
REGION="us-central1"
JOB="informe-mensual"
SA="finanzas-app@${PROYECTO}.iam.gserviceaccount.com"
SMTP_USUARIO="$1"
PARA="$2"

cd "$(dirname "$0")/.."

# Usa la misma imagen de la app, con otro comando
IMAGEN="$(gcloud run services describe finanzas-str --region "$REGION" --format='value(spec.template.spec.containers[0].image)')"

gcloud run jobs deploy "$JOB" \
  --image "$IMAGEN" \
  --region "$REGION" \
  --service-account "$SA" \
  --command python --args informe/informe_mensual.py \
  --max-retries 1 --task-timeout 600 \
  --set-env-vars "GCP_PROYECTO=${PROYECTO},BQ_DATASET=finanzas,CLAUDE_MODEL=claude-haiku-5-5,SMTP_USUARIO=${SMTP_USUARIO},INFORME_PARA=${PARA}" \
  --set-secrets "ANTHROPIC_API_KEY=anthropic-api-key:latest,SMTP_PASSWORD=smtp-password:latest"

# Cloud Scheduler usa la misma cuenta de servicio para lanzar el Job
gcloud run jobs add-iam-policy-binding "$JOB" --region "$REGION" \
  --member="serviceAccount:$SA" --role="roles/run.invoker" >/dev/null

gcloud scheduler jobs describe "$JOB" --location "$REGION" >/dev/null 2>&1 && \
  gcloud scheduler jobs delete "$JOB" --location "$REGION" --quiet

gcloud scheduler jobs create http "$JOB" \
  --location "$REGION" \
  --schedule "0 9 5 * *" --time-zone "America/Santiago" \
  --uri "https://run.googleapis.com/v2/projects/${PROYECTO}/locations/${REGION}/jobs/${JOB}:run" \
  --http-method POST \
  --oauth-service-account-email "$SA"

echo "Programado. Para probarlo ahora:  gcloud run jobs execute $JOB --region $REGION"

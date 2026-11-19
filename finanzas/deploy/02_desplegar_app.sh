#!/usr/bin/env bash
# =====================================================================
# 02_desplegar_app.sh — Publica (o actualiza) la app en Cloud Run con login de Google (IAP).
# Uso:  bash deploy/02_desplegar_app.sh "tu-email@gmail.com,email-jefa@gmail.com"
# Vuelve a ejecutarlo cada vez que cambies el código.
# =====================================================================
set -euo pipefail

PROYECTO="$(gcloud config get-value project)"
REGION="us-central1"
SERVICIO="finanzas-str"
SA="finanzas-app@${PROYECTO}.iam.gserviceaccount.com"
NUMERO_PROYECTO="$(gcloud projects describe "$PROYECTO" --format='value(projectNumber)')"
USUARIOS="${1:-}"
# Usa la API de Claude solo si existe el secreto (si no, la app funciona sin IA integrada)
SECRETOS=()
if gcloud secrets describe anthropic-api-key >/dev/null 2>&1; then
  SECRETOS=(--set-secrets "ANTHROPIC_API_KEY=anthropic-api-key:latest")
fi

cd "$(dirname "$0")/.."

gcloud run deploy "$SERVICIO" \
  --source . \
  --region "$REGION" \
  --service-account "$SA" \
  --no-allow-unauthenticated \
  --iap \
  --min-instances 0 --max-instances 1 \
  --cpu 1 --memory 1Gi \
  --timeout 3600 --session-affinity \
  --set-env-vars "GCP_PROYECTO=${PROYECTO},BQ_DATASET=finanzas,BUCKET_BOLETAS=${PROYECTO}-boletas,CLAUDE_MODEL=claude-haiku-5-5" \
  "${SECRETOS[@]}"

# IAP necesita permiso para invocar el servicio
gcloud run services add-iam-policy-binding "$SERVICIO" --region "$REGION" \
  --member="serviceAccount:service-${NUMERO_PROYECTO}@gcp-sa-iap.iam.gserviceaccount.com" \
  --role="roles/run.invoker" >/dev/null

# Dar acceso a cada persona (además deben estar en la tabla finanzas.usuarios)
IFS=',' read -ra LISTA <<< "$USUARIOS"
for EMAIL in "${LISTA[@]}"; do
  [ -z "$EMAIL" ] && continue
  gcloud iap web add-iam-policy-binding \
    --resource-type=cloud-run --service="$SERVICIO" --region="$REGION" \
    --member="user:${EMAIL}" --role="roles/iap.httpsResourceAccessor" >/dev/null
  echo "Acceso dado a $EMAIL"
done

echo
echo "URL de la app:"
gcloud run services describe "$SERVICIO" --region "$REGION" --format='value(status.url)'

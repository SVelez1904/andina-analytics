#!/usr/bin/env bash
# =====================================================================
# 04_github_cicd.sh — Conecta tu repositorio de GitHub con GCP SIN llaves (Workload Identity Federation)
# para que GitHub Actions pueda desplegar. Se ejecuta UNA vez, después de 01 y 02.
# Uso:  bash deploy/04_github_cicd.sh TU_USUARIO_GITHUB/NOMBRE_REPO
# Requiere: gcloud autenticado; opcional: gh (GitHub CLI) autenticado para crear las variables solo.
# =====================================================================
set -euo pipefail

REPO="${1:?Indica el repositorio, ej: SVelez1904/andina-analytics}"
PROYECTO="$(gcloud config get-value project)"
NUMERO="$(gcloud projects describe "$PROYECTO" --format='value(projectNumber)')"
REGION="us-central1"
POOL="github"
PROVEEDOR="github-oidc"
SA_DEPLOY="github-deployer@${PROYECTO}.iam.gserviceaccount.com"
SA_APP="finanzas-app@${PROYECTO}.iam.gserviceaccount.com"
SA_BUILD="${NUMERO}-compute@developer.gserviceaccount.com"

gcloud services enable iamcredentials.googleapis.com sts.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

# 1) Pool y proveedor OIDC: SOLO tu repositorio puede pedir credenciales
gcloud iam workload-identity-pools describe "$POOL" --location=global >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools create "$POOL" --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers describe "$PROVEEDOR" --location=global --workload-identity-pool="$POOL" >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools providers create-oidc "$PROVEEDOR" \
    --location=global --workload-identity-pool="$POOL" \
    --display-name="GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository == '${REPO}'"

# 2) Cuenta de servicio que usa GitHub para desplegar (separada de la de la app)
gcloud iam service-accounts describe "$SA_DEPLOY" >/dev/null 2>&1 || \
  gcloud iam service-accounts create github-deployer --display-name="GitHub Actions deployer"

gcloud iam service-accounts add-iam-policy-binding "$SA_DEPLOY" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${NUMERO}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${REPO}" >/dev/null

for ROL in roles/run.admin roles/cloudbuild.builds.editor roles/artifactregistry.admin \
           roles/storage.admin roles/serviceusage.serviceUsageConsumer roles/bigquery.jobUser roles/logging.viewer; do
  gcloud projects add-iam-policy-binding "$PROYECTO" --member="serviceAccount:$SA_DEPLOY" --role="$ROL" --condition=None >/dev/null
done
# Puede "actuar como" la cuenta de la app y la de Cloud Build (necesario para desplegar)
for SA in "$SA_APP" "$SA_BUILD"; do
  gcloud iam service-accounts add-iam-policy-binding "$SA" --member="serviceAccount:$SA_DEPLOY" --role="roles/iam.serviceAccountUser" >/dev/null
done

# 3) Mantener Artifact Registry dentro del nivel gratuito: guardar solo las 2 imágenes más recientes
cat > /tmp/limpieza-imagenes.json <<'JSON'
[
  {"name": "conservar-recientes", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}},
  {"name": "borrar-antiguas", "action": {"type": "Delete"}, "condition": {"olderThan": "1d"}}
]
JSON
if gcloud artifacts repositories describe cloud-run-source-deploy --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy --location="$REGION" \
    --policy=/tmp/limpieza-imagenes.json --no-dry-run
fi

# 4) Dataset de pruebas para las vistas previas de los PR (copia instantánea con CLONE)
sed "s/TU_PROYECTO/${PROYECTO}/g" sql/99_dataset_pruebas.sql | bq query --use_legacy_sql=false --quiet
sed -e "s/TU_PROYECTO/${PROYECTO}/g" -e 's/\.finanzas\./.finanzas_dev./g' sql/03_vistas.sql | bq query --use_legacy_sql=false --quiet
bq query --use_legacy_sql=false --quiet \
  "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`${PROYECTO}.finanzas_dev\` TO \"serviceAccount:${SA_APP}\""
bq query --use_legacy_sql=false --quiet \
  "GRANT \`roles/bigquery.dataViewer\` ON SCHEMA \`${PROYECTO}.finanzas\` TO \"serviceAccount:${SA_DEPLOY}\""

PROVIDER_ID="projects/${NUMERO}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVEEDOR}"

# 5) Variables del repositorio (no son secretos: no contienen llaves)
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh variable set GCP_PROYECTO     --repo "$REPO" --body "$PROYECTO"
  gh variable set GCP_WIF_PROVIDER --repo "$REPO" --body "$PROVIDER_ID"
  gh variable set GCP_SA_DEPLOY    --repo "$REPO" --body "$SA_DEPLOY"
  echo "Variables creadas en GitHub."
else
  echo "Crea estas 3 variables en GitHub → Settings → Secrets and variables → Actions → Variables:"
  echo "  GCP_PROYECTO     = $PROYECTO"
  echo "  GCP_WIF_PROVIDER = $PROVIDER_ID"
  echo "  GCP_SA_DEPLOY    = $SA_DEPLOY"
fi
echo "Listo. Haz un push a main para desplegar, o abre un PR para ver la vista previa."

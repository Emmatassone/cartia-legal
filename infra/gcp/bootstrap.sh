#!/usr/bin/env bash
#
# Bootstrap de la infraestructura GCP de CartIA Legal. Se corre UNA sola vez por proyecto.
#
# Deja armado todo lo que los workflows de GitHub Actions dan por hecho:
#   - APIs habilitadas
#   - repositorio de Artifact Registry
#   - service accounts de runtime (una por servicio, con permisos mínimos)
#   - Workload Identity Federation para que GitHub Actions despliegue sin claves JSON
#
# Uso:
#   export GCP_PROJECT_ID=mi-proyecto
#   export GITHUB_REPO=usuario/cartia-legal
#   bash infra/gcp/bootstrap.sh
#
# Al final imprime los valores exactos que hay que cargar como GitHub Variables.

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?definí GCP_PROJECT_ID}"
GITHUB_REPO="${GITHUB_REPO:?definí GITHUB_REPO con el formato usuario/repo}"
REGION="${GCP_REGION:-southamerica-east1}"
GAR_REPOSITORY="${GAR_REPOSITORY:-cartia-containers}"
POOL="${WIF_POOL:-github-pool}"
PROVIDER="${WIF_PROVIDER:-github-provider}"
DEPLOY_SA="cartia-deployer"

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

echo "==> Proyecto $PROJECT_ID ($PROJECT_NUMBER), región $REGION"

echo "==> Habilitando APIs"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  secretmanager.googleapis.com \
  generativelanguage.googleapis.com \
  --project="$PROJECT_ID"

echo "==> Artifact Registry"
gcloud artifacts repositories describe "$GAR_REPOSITORY" \
  --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$GAR_REPOSITORY" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Imágenes de CartIA Legal" \
    --project="$PROJECT_ID"

# Una SA de runtime por servicio: si se compromete el backend, no queda con los permisos
# del loader (que puede borrar el índice completo).
create_sa() {
  local name="$1" display="$2"
  gcloud iam service-accounts describe "${name}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project="$PROJECT_ID" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$name" \
      --display-name="$display" \
      --project="$PROJECT_ID"
}

echo "==> Service accounts de runtime"
create_sa cartia-backend "CartIA Backend (Cloud Run)"
create_sa cartia-rag "CartIA RAG (Cloud Run)"
create_sa cartia-rag-loader "CartIA RAG Loader (Cloud Run Job)"

echo "==> Service account de deploy"
create_sa "$DEPLOY_SA" "CartIA GitHub Actions deployer"

DEPLOY_SA_EMAIL="${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

for role in \
  roles/run.admin \
  roles/artifactregistry.writer \
  roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${DEPLOY_SA_EMAIL}" \
    --role="$role" \
    --condition=None \
    --quiet >/dev/null
done

# El backend invoca al servicio RAG, que se despliega privado.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:cartia-backend@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --condition=None \
  --quiet >/dev/null

echo "==> Workload Identity Federation"
gcloud iam workload-identity-pools describe "$POOL" \
  --location=global --project="$PROJECT_ID" >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools create "$POOL" \
    --location=global \
    --display-name="GitHub Actions" \
    --project="$PROJECT_ID"

# La condición sobre `assertion.repository` es lo que impide que otro repositorio de
# GitHub obtenga credenciales de este proyecto. Sin ella, el pool queda abierto.
gcloud iam workload-identity-pools providers describe "$PROVIDER" \
  --location=global --workload-identity-pool="$POOL" --project="$PROJECT_ID" >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --location=global \
    --workload-identity-pool="$POOL" \
    --display-name="GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository == '${GITHUB_REPO}'" \
    --project="$PROJECT_ID"

gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${GITHUB_REPO}" \
  --project="$PROJECT_ID" \
  --quiet >/dev/null

WIF_PROVIDER_PATH="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}"

cat <<EOF

=====================================================================
Listo. Cargá estas GitHub Variables (Settings > Environments > Production):

  GCP_PROJECT_ID                        ${PROJECT_ID}
  GCP_REGION                            ${REGION}
  GAR_REPOSITORY                        ${GAR_REPOSITORY}
  GCP_WIF_PROVIDER                      ${WIF_PROVIDER_PATH}
  GCP_DEPLOY_SA                         ${DEPLOY_SA_EMAIL}
  BACKEND_RUNTIME_SERVICE_ACCOUNT       cartia-backend@${PROJECT_ID}.iam.gserviceaccount.com
  RAG_RUNTIME_SERVICE_ACCOUNT           cartia-rag@${PROJECT_ID}.iam.gserviceaccount.com
  RAG_LOADER_RUNTIME_SERVICE_ACCOUNT    cartia-rag-loader@${PROJECT_ID}.iam.gserviceaccount.com
  EMBEDDING_DIMENSIONS                  1536

Y estos GitHub Secrets:

  BACKEND_DATABASE_URL   RAG_DATABASE_URL   JWT_SECRET
  GOOGLE_API_KEY         INTERNAL_TOKEN
  VERCEL_TOKEN           VERCEL_ORG_ID      VERCEL_PROJECT_ID

Después del primer deploy del backend y del RAG, completá las variables que dependen
de las URLs generadas: RAG_SERVICE_URL, CORS_ORIGINS y NEXT_PUBLIC_API_URL.
=====================================================================
EOF

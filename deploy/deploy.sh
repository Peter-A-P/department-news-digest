#!/usr/bin/env bash
# Deploy the digest to Google Cloud Run: one bucket, one image, a daily job, a read-only
# service, and the schedule. PLAN.md section 2.5; the walk-through is deploy/README.md.
#
# Idempotent where gcloud allows: a resource that already exists is left as it is, and the
# job and service are redeployed with the new image.
#
# Required:
#   PROJECT         the Google Cloud project id
#   BILLING_ACCOUNT the billing account id, for the budget alert
# Optional:
#   REGION          default us-east1, where Cloud Storage's free tier applies
#   BUCKET          default $PROJECT-clippings
#   SCHEDULE        default "0 9 * * *" (09:00 UTC, before 07:00 in St. John's and Toronto)
#   BUDGET_CAD      default 10, the monthly budget the alert fires against
#
# Secrets are created empty-handed: this script never sees a key. Add each value with
#   printf %s "$VALUE" | gcloud secrets versions add NAME --data-file=-
# before the first run. See deploy/README.md.

set -euo pipefail

: "${PROJECT:?set PROJECT to the Google Cloud project id}"
: "${BILLING_ACCOUNT:?set BILLING_ACCOUNT for the budget alert}"
REGION="${REGION:-us-east1}"
BUCKET="${BUCKET:-${PROJECT}-clippings}"
SCHEDULE="${SCHEDULE:-0 9 * * *}"
BUDGET_CAD="${BUDGET_CAD:-10}"
REPO="${REGION}-docker.pkg.dev/${PROJECT}/clippings"
TAG="$(git rev-parse --short HEAD)"
IMAGE="${REPO}/clippings:${TAG}"
JOB_SA="clippings-job@${PROJECT}.iam.gserviceaccount.com"
WEB_SA="clippings-web@${PROJECT}.iam.gserviceaccount.com"
SCHEDULER_SA="clippings-scheduler@${PROJECT}.iam.gserviceaccount.com"
SECRETS=(anthropic-api-key reddit-client-id reddit-client-secret bluesky-handle bluesky-app-password)

gcloud config set project "$PROJECT" >/dev/null

echo "== APIs"
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com billingbudgets.googleapis.com

echo "== Budget alert first, before anything can cost money"
if ! gcloud billing budgets list --billing-account="$BILLING_ACCOUNT" \
    --format="value(displayName)" | grep -qx "clippings"; then
  gcloud billing budgets create --billing-account="$BILLING_ACCOUNT" \
    --display-name="clippings" --budget-amount="${BUDGET_CAD}CAD" \
    --filter-projects="projects/${PROJECT}" \
    --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
fi

echo "== Bucket: state, the run lock and the published site. Private; the service reads it."
gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${BUCKET}" --location="$REGION" \
    --uniform-bucket-level-access --public-access-prevention

echo "== Service accounts, each with only what it needs"
for sa in clippings-job clippings-web clippings-scheduler; do
  gcloud iam service-accounts describe "${sa}@${PROJECT}.iam.gserviceaccount.com" >/dev/null 2>&1 || \
    gcloud iam service-accounts create "$sa" --display-name="$sa"
done
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${JOB_SA}" --role=roles/storage.objectAdmin >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${WEB_SA}" --role=roles/storage.objectViewer >/dev/null

echo "== Secrets (names only; values are added by hand)"
for secret in "${SECRETS[@]}"; do
  gcloud secrets describe "$secret" >/dev/null 2>&1 || \
    gcloud secrets create "$secret" --replication-policy=automatic
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${JOB_SA}" --role=roles/secretmanager.secretAccessor >/dev/null
done

echo "== Image"
gcloud artifacts repositories describe clippings --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create clippings --repository-format=docker --location="$REGION"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker build --platform linux/amd64 -f deploy/Dockerfile -t "$IMAGE" .
docker push "$IMAGE"

echo "== The daily job"
# Only secrets that hold a value are mapped: Cloud Run refuses to start a job whose secret
# has no version, and Reddit and Bluesky are optional (the run carries on without them).
has_value() { [ -n "$(gcloud secrets versions list "$1" --limit=1 --format='value(name)')" ]; }
has_value anthropic-api-key || { echo "add a value to the anthropic-api-key secret first" >&2; exit 1; }
MAPPED="ANTHROPIC_API_KEY=anthropic-api-key:latest"
for pair in REDDIT_CLIENT_ID=reddit-client-id REDDIT_CLIENT_SECRET=reddit-client-secret \
    BLUESKY_HANDLE=bluesky-handle BLUESKY_APP_PASSWORD=bluesky-app-password; do
  if has_value "${pair#*=}"; then MAPPED="${MAPPED},${pair}:latest"; fi
done
# CLIPPINGS_ALLOW_SPEND is the switch; the caps in clippings/config/gateway/caps.yaml are the
# limit. One retry: a second attempt on a transient failure is cheap, and the per-run and
# per-day caps bound what a retry can spend.
gcloud run jobs deploy clippings-daily --image="$IMAGE" --region="$REGION" \
  --service-account="$JOB_SA" --command=clippings --args=run \
  --set-env-vars="CLIPPINGS_BUCKET=${BUCKET},CLIPPINGS_ALLOW_SPEND=1,BOUNDARY_ENV=cloudrun" \
  --set-secrets="$MAPPED" \
  --cpu=1 --memory=2Gi --task-timeout=3600 --max-retries=1

echo "== The schedule"
gcloud run jobs add-iam-policy-binding clippings-daily --region="$REGION" \
  --member="serviceAccount:${SCHEDULER_SA}" --role=roles/run.invoker >/dev/null
RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/clippings-daily:run"
if gcloud scheduler jobs describe clippings-daily --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http clippings-daily --location="$REGION" \
    --schedule="$SCHEDULE" --time-zone=UTC --uri="$RUN_URI" --http-method=POST \
    --oauth-service-account-email="$SCHEDULER_SA"
else
  gcloud scheduler jobs create http clippings-daily --location="$REGION" \
    --schedule="$SCHEDULE" --time-zone=UTC --uri="$RUN_URI" --http-method=POST \
    --oauth-service-account-email="$SCHEDULER_SA"
fi

echo "== The read-only service"
gcloud run deploy clippings-web --image="$IMAGE" --region="$REGION" \
  --service-account="$WEB_SA" --set-env-vars="CLIPPINGS_BUCKET=${BUCKET}" \
  --allow-unauthenticated --cpu=1 --memory=512Mi --min-instances=0 --max-instances=2

echo
echo "Deployed ${IMAGE}."
echo "Run once by hand:  gcloud run jobs execute clippings-daily --region=${REGION} --wait"
echo "The pages:         $(gcloud run services describe clippings-web --region="$REGION" --format='value(status.url)')"

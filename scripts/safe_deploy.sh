#!/usr/bin/env bash
# Deploy guard: refuse to replace the web service while analyses are in flight.
# With RUN_MODE=worker this mostly protects legacy in-process and writer runs —
# worker-job runs survive deploys by construction — but the check costs nothing
# and has been fumbled by hand twice, so it is now the only sanctioned path.
set -euo pipefail

REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-greenlight}"

# Gate on green: a red test or lint error must stop a deploy MECHANICALLY.
# "pytest | tail" has hidden a failing exit code from a human twice now —
# the guard belongs in the tool, not in discipline.
echo "safe_deploy: running tests + checks first..."
.venv/bin/python -m pytest -q || { echo "safe_deploy: TESTS RED — refusing to deploy."; exit 1; }
make check || { echo "safe_deploy: CHECKS RED — refusing to deploy."; exit 1; }

busy=$(curl -sf --max-time 10 https://scriptrisk.com/api/metrics-lite \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('running_now', 0))" \
  2>/dev/null || echo "unknown")

if [ "$busy" = "unknown" ]; then
  echo "safe_deploy: could not read live-run status — refusing. (--force to override)"
  [ "${1:-}" = "--force" ] || exit 1
elif [ "$busy" != "0" ]; then
  echo "safe_deploy: $busy analysis(es) in flight — refusing to deploy. (--force to override)"
  [ "${1:-}" = "--force" ] || exit 1
fi

gcloud run deploy "$SERVICE" --source . --region "$REGION" --quiet

# keep the worker job on the same image as the service
IMG=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format='value(spec.template.spec.containers[0].image)')
gcloud run jobs update greenlight-worker --image "$IMG" --region "$REGION" --quiet
echo "safe_deploy: service + worker job on image ${IMG##*/}"

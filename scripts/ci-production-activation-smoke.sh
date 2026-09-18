#!/usr/bin/env bash
# Disposable CI-only topology. No production host, credentials, or data.
set -Eeuo pipefail
cd -- "$(dirname "$0")/.."
sha="${1:?exact image SHA required}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]]
project="munshi-ci-smoke-${GITHUB_RUN_ID:-local}-$$"
export MUNSHI_APPLY_IMAGE_REPOSITORY=munshi-apply-ci
export MUNSHI_APPLY_IMAGE_TAG="$sha" MUNSHI_APPLY_DEPLOY_SHA="$sha"
export MUNSHI_HUNTER_NETWORK_NAME="$project-internal"
export MUNSHI_APPLY_BIND_HOST=127.0.0.1 MUNSHI_APPLY_PUBLISHED_PORT=8505
export MUNSHI_HUNTER_EXECUTION_BRIDGE_BASE_URL=http://hunter:8000
export MUNSHI_APPLY_COMMAND_SECRET=ci-only-command-secret-not-production-000000000000
export MUNSHI_APPLY_HANDOFF_HMAC_SECRET=ci-only-handoff-secret-not-production-000000000000
export MUNSHI_PRODUCTION_SUBMIT_AUTH_HMAC_SECRET=ci-only-authority-secret-not-production-0000000000
export MUNSHI_PRODUCTION_RECEIPT_HMAC_SECRET=ci-only-receipt-secret-not-production-000000000000
export MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED=false
compose=(docker compose --project-name "$project" -f deploy/production/compose.yaml --profile hosted-prepare --profile hosted-submit)
cleanup() {
  rc=$?
  trap - EXIT
  if (( rc )); then "${compose[@]}" logs --tail 100 || true; fi
  # Only this randomly named CI fixture's resources are removed.
  "${compose[@]}" down -v >/dev/null 2>&1 || true
  docker network rm "$MUNSHI_HUNTER_NETWORK_NAME" >/dev/null 2>&1 || true
  exit "$rc"
}
trap cleanup EXIT
docker network create --internal "$MUNSHI_HUNTER_NETWORK_NAME" >/dev/null
"${compose[@]}" up -d --no-build apply prepare-worker
api="$("${compose[@]}" ps -q apply)"
for _ in $(seq 1 60); do
  health="$(docker inspect -f '{{.State.Health.Status}}' "$api")"
  [[ "$health" == healthy ]] && break
  sleep 2
done
[[ "$health" == healthy ]]
docker exec "$api" python /app/scripts/runtime-ops.py health --database /data/munshi-apply.sqlite --migrations /app/migrations
export MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED=true
"${compose[@]}" up -d --no-build --no-deps --force-recreate apply
"${compose[@]}" up -d --no-build submit-worker
sleep 5
for service in apply prepare-worker submit-worker; do
  id="$("${compose[@]}" ps -q "$service")"
  [[ -n "$id" ]]
  [[ "$(docker inspect -f '{{.State.Running}}|{{.RestartCount}}|{{.State.OOMKilled}}' "$id")" == 'true|0|false' ]]
  [[ "$(docker inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$id")" == "$sha" ]]
done
api="$("${compose[@]}" ps -q apply)"
docker exec -i "$api" python - <<'PY'
import sqlite3
db = sqlite3.connect("file:/data/munshi-apply.sqlite?mode=ro", uri=True)
assert db.execute("SELECT COUNT(*) FROM complete_application_sessions").fetchone()[0] == 0
assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
print("CI_PRODUCTION_API_PREPARE_SUBMIT_IDLE_SMOKE=PASS")
print("REAL_APPLICATIONS_SUBMITTED=0")
PY

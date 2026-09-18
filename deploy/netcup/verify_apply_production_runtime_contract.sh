#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${MUNSHI_APPLY_PRODUCTION_ROOT:-/opt/munshi/apply-production}"
REPO="$ROOT/repo"
ENV_FILE="${MUNSHI_APPLY_PRODUCTION_ENV_FILE:-$ROOT/runtime/production.env}"
PROJECT="${MUNSHI_APPLY_PRODUCTION_PROJECT:-munshi-apply-production}"
EXPECTED_SHA=""
EXPECT_SUBMIT="off"

while (($#)); do
  case "$1" in
    --expected-sha) EXPECTED_SHA="${2:-}"; shift 2 ;;
    --expect-submit) EXPECT_SUBMIT="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ "$EXPECT_SUBMIT" == "on" || "$EXPECT_SUBMIT" == "off" ]] || {
  echo "--expect-submit must be on|off" >&2; exit 3;
}
[[ -d "$REPO/.git" ]] || { echo "Apply production repo missing: $REPO" >&2; exit 10; }
[[ -f "$ENV_FILE" && -r "$ENV_FILE" ]] || { echo "Apply production env missing: $ENV_FILE" >&2; exit 11; }
[[ -f "$REPO/deploy/production/compose.yaml" ]] || { echo "Apply production compose missing" >&2; exit 12; }

if [[ -z "$EXPECTED_SHA" ]]; then EXPECTED_SHA="$(git -c "safe.directory=$REPO" -C "$REPO" rev-parse HEAD)"; fi
[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "expected SHA invalid" >&2; exit 13; }
[[ "$(git -c "safe.directory=$REPO" -C "$REPO" rev-parse HEAD)" == "$EXPECTED_SHA" ]] || { echo "Apply production checkout SHA mismatch" >&2; exit 14; }
[[ -z "$(git -c "safe.directory=$REPO" -C "$REPO" status --porcelain)" ]] || { echo "Apply production repo dirty" >&2; exit 15; }

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${MUNSHI_APPLY_IMAGE_REPOSITORY:=munshi-apply-production}"
: "${MUNSHI_APPLY_BIND_HOST:=127.0.0.1}"
: "${MUNSHI_APPLY_PUBLISHED_PORT:=8505}"
: "${MUNSHI_HUNTER_NETWORK_NAME:=munshi-netcup-shadow_application}"

for key in MUNSHI_APPLY_COMMAND_SECRET MUNSHI_APPLY_HANDOFF_HMAC_SECRET MUNSHI_PRODUCTION_SUBMIT_AUTH_HMAC_SECRET MUNSHI_PRODUCTION_RECEIPT_HMAC_SECRET; do
  value="${!key:-}"
  [[ "${#value}" -ge 32 ]] || { echo "required production secret missing/too short: $key" >&2; exit 16; }
done
[[ "${MUNSHI_HUNTER_EXECUTION_BRIDGE_BASE_URL:-}" == "http://hunter:8000" ]] || {
  echo "Hunter production bridge URL must be http://hunter:8000" >&2; exit 17;
}
docker network inspect "$MUNSHI_HUNTER_NETWORK_NAME" >/dev/null 2>&1 || {
  echo "Hunter production application network missing: $MUNSHI_HUNTER_NETWORK_NAME" >&2; exit 18;
}

compose=(
  docker compose
  --project-name "$PROJECT"
  --env-file "$ENV_FILE"
  -f "$REPO/deploy/production/compose.yaml"
)

MUNSHI_APPLY_DEPLOY_SHA="$EXPECTED_SHA" MUNSHI_APPLY_IMAGE_TAG="$EXPECTED_SHA"   "${compose[@]}" --profile hosted-prepare --profile hosted-submit config -q

api_id="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=apply' | head -n1)"
prepare_id="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=prepare-worker' | head -n1)"
submit_id="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=submit-worker' | head -n1)"

[[ -n "$api_id" ]] || { echo "Apply production API is not running" >&2; exit 20; }
[[ -n "$prepare_id" ]] || { echo "Apply production prepare worker is not running" >&2; exit 21; }

api_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$api_id")"
[[ "$api_health" == "healthy" ]] || { echo "Apply production API unhealthy: $api_health" >&2; exit 22; }
api_revision="$(docker inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$api_id")"
[[ "$api_revision" == "$EXPECTED_SHA" ]] || { echo "Apply production image revision mismatch" >&2; exit 23; }

for id in "$api_id" "$prepare_id"; do
  running="$(docker inspect -f '{{.State.Running}}' "$id")"
  oom="$(docker inspect -f '{{.State.OOMKilled}}' "$id")"
  [[ "$running" == "true" && "$oom" == "false" ]] || { echo "Apply production service unhealthy: $id" >&2; exit 24; }
  docker inspect -f '{{json .NetworkSettings.Networks}}' "$id" | grep -Fq "$MUNSHI_HUNTER_NETWORK_NAME" || {
    echo "Apply production service is not on Hunter production network: $id" >&2; exit 25;
  }
done

api_env="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api_id")"
grep -qx 'MUNSHI_ENVIRONMENT=production' <<<"$api_env"
grep -qx 'MUNSHI_FINAL_REVIEW_ENABLED=true' <<<"$api_env"
grep -qx 'MUNSHI_FINAL_SUBMIT_ENABLED=false' <<<"$api_env"

prepare_env="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$prepare_id")"
for kv in   'MUNSHI_ENVIRONMENT=production'   'MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED=true'   'MUNSHI_APPLY_HOSTED_PREPARE_WORKER_ENABLED=true'   'MUNSHI_APPLY_RESUME_UPLOAD_ENABLED=true'   'MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED=true'   'MUNSHI_FINAL_SUBMIT_ENABLED=false'
do
  grep -qx "$kv" <<<"$prepare_env" || { echo "prepare worker contract mismatch: $kv" >&2; exit 26; }
done

if [[ "$EXPECT_SUBMIT" == "on" ]]; then
  [[ -n "$submit_id" ]] || { echo "Apply production submit worker is not running" >&2; exit 30; }
  submit_env="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$submit_id")"
  for kv in     'MUNSHI_ENVIRONMENT=production'     'MUNSHI_APPLY_HOSTED_SUBMIT_WORKER_ENABLED=true'     'MUNSHI_FINAL_REVIEW_ENABLED=true'     'MUNSHI_FINAL_SUBMIT_ENABLED=true'     'MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED=true'     'MUNSHI_APPLY_RESUME_UPLOAD_ENABLED=true'     'MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED=true'
  do
    grep -qx "$kv" <<<"$submit_env" || { echo "submit worker contract mismatch: $kv" >&2; exit 31; }
  done
  api_env="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api_id")"
  grep -qx 'MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED=true' <<<"$api_env" || {
    echo "Apply API submit-authority ingest is not enabled" >&2; exit 32;
  }
  echo "APPLY_PRODUCTION_SUBMIT_WORKER_ACTIVE=YES"
else
  [[ -z "$submit_id" ]] || { echo "Apply production submit worker active before final gate" >&2; exit 33; }
  echo "APPLY_PRODUCTION_SUBMIT_WORKER_ACTIVE=NO"
fi

python3 - "$MUNSHI_APPLY_BIND_HOST" "$MUNSHI_APPLY_PUBLISHED_PORT" <<'PY'
import sys, urllib.request
with urllib.request.urlopen(f"http://{sys.argv[1]}:{sys.argv[2]}/health", timeout=10) as response:
    if response.status != 200:
        raise SystemExit(f"Apply production health returned {response.status}")
print("APPLY_PRODUCTION_HTTP_HEALTH=PASS")
PY

docker exec "$api_id" python /app/scripts/runtime-ops.py health   --database /data/munshi-apply.sqlite   --migrations /app/migrations >/dev/null

echo "APPLY_PRODUCTION_DATABASE_HEALTH=PASS"
echo "APPLY_PRODUCTION_IMAGE_REVISION=$api_revision"
echo "APPLY_PRODUCTION_EXPECT_SUBMIT=$EXPECT_SUBMIT"
echo "RESULT=APPLY_PRODUCTION_RUNTIME_CONTRACT_PASS"
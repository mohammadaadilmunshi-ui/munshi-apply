#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

TARGET_CONFIG_DIR="${MUNSHI_APPLY_DEPLOY_TARGET_CONFIG_DIR:-/opt/munshi/deploy-targets}"
target=""
TARGET_CONFIG=""
PROJECT=""
STAGING_ROOT=""
STAGING_REPO=""
STAGING_ENV=""
HUNTER_NETWORK=""
IMAGE_REPOSITORY=""
BIND_HOST=""
PUBLISHED_PORT=""
DEPLOY_ENVIRONMENT=""
RUNTIME_ENV_FILE=""

target_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "$TARGET_CONFIG" | tail -n1 || true)"
  [[ -n "$line" ]] || { echo "deployment target is missing $key: $TARGET_CONFIG" >&2; exit 7; }
  local value="${line#*=}"
  [[ -n "$value" ]] || { echo "deployment target has empty $key: $TARGET_CONFIG" >&2; exit 7; }
  printf '%s' "$value"
}

load_target_config() {
  [[ "$target" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { echo "--target invalid" >&2; exit 4; }
  TARGET_CONFIG="$TARGET_CONFIG_DIR/apply-$target.env"
  [[ -f "$TARGET_CONFIG" && -r "$TARGET_CONFIG" ]] || { echo "Apply deployment target config missing: $TARGET_CONFIG" >&2; exit 7; }

  STAGING_ROOT="$(target_value MUNSHI_APPLY_DEPLOY_ROOT)"
  PROJECT="$(target_value MUNSHI_APPLY_COMPOSE_PROJECT)"
  BIND_HOST="$(target_value MUNSHI_APPLY_BIND_HOST)"
  PUBLISHED_PORT="$(target_value MUNSHI_APPLY_PUBLISHED_PORT)"
  HUNTER_NETWORK="$(target_value MUNSHI_HUNTER_NETWORK_NAME)"
  IMAGE_REPOSITORY="$(target_value MUNSHI_APPLY_IMAGE_REPOSITORY)"
  DEPLOY_ENVIRONMENT="$(target_value MUNSHI_ENVIRONMENT)"
  RUNTIME_ENV_FILE="$(target_value MUNSHI_APPLY_RUNTIME_ENV_FILE)"

  [[ "$STAGING_ROOT" == /* && "$STAGING_ROOT" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "invalid MUNSHI_APPLY_DEPLOY_ROOT" >&2; exit 7; }
  [[ "$PROJECT" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || { echo "invalid MUNSHI_APPLY_COMPOSE_PROJECT" >&2; exit 7; }
  [[ "$BIND_HOST" =~ ^[0-9A-Fa-f:.]+$ ]] || { echo "invalid MUNSHI_APPLY_BIND_HOST" >&2; exit 7; }
  [[ "$PUBLISHED_PORT" =~ ^[0-9]{1,5}$ ]] || { echo "invalid MUNSHI_APPLY_PUBLISHED_PORT" >&2; exit 7; }
  (( 10#$PUBLISHED_PORT >= 1 && 10#$PUBLISHED_PORT <= 65535 )) || { echo "MUNSHI_APPLY_PUBLISHED_PORT out of range" >&2; exit 7; }
  [[ "$HUNTER_NETWORK" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || { echo "invalid MUNSHI_HUNTER_NETWORK_NAME" >&2; exit 7; }
  [[ "$IMAGE_REPOSITORY" =~ ^[A-Za-z0-9._/-]+$ ]] || { echo "invalid MUNSHI_APPLY_IMAGE_REPOSITORY" >&2; exit 7; }
  [[ "$DEPLOY_ENVIRONMENT" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid MUNSHI_ENVIRONMENT" >&2; exit 7; }
  [[ "$RUNTIME_ENV_FILE" == /* && "$RUNTIME_ENV_FILE" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "invalid MUNSHI_APPLY_RUNTIME_ENV_FILE" >&2; exit 7; }
  [[ "$RUNTIME_ENV_FILE" == "$STAGING_ROOT/"* ]] || { echo "MUNSHI_APPLY_RUNTIME_ENV_FILE must stay inside deployment root" >&2; exit 7; }

  STAGING_REPO="$STAGING_ROOT/repo"
  STAGING_ENV="$RUNTIME_ENV_FILE"

  export MUNSHI_APPLY_COMPOSE_PROJECT="$PROJECT"
  export MUNSHI_APPLY_BIND_HOST="$BIND_HOST"
  export MUNSHI_APPLY_PUBLISHED_PORT="$PUBLISHED_PORT"
  export MUNSHI_HUNTER_NETWORK_NAME="$HUNTER_NETWORK"
  export MUNSHI_APPLY_IMAGE_REPOSITORY="$IMAGE_REPOSITORY"
  export MUNSHI_ENVIRONMENT="$DEPLOY_ENVIRONMENT"
}
EXPECTED_SHA=""



while (($#)); do
  case "$1" in
    --target) target="${2:-}"; shift 2 ;;
    --expected-sha) EXPECTED_SHA="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

load_target_config

[[ -d "$STAGING_REPO/.git" ]] || { echo "Apply staging repository missing: $STAGING_REPO" >&2; exit 10; }
[[ -f "$STAGING_ENV" ]] || { echo "Apply staging env file missing: $STAGING_ENV" >&2; exit 11; }
[[ -r "$STAGING_ENV" ]] || { echo "Apply staging env file is not readable by the deployment user: $STAGING_ENV" >&2; exit 12; }
[[ -f "$STAGING_REPO/deploy/staging/compose.yaml" ]] || { echo "Apply staging compose file missing" >&2; exit 13; }

if [[ -z "$EXPECTED_SHA" ]]; then
  EXPECTED_SHA="$(git -C "$STAGING_REPO" rev-parse HEAD)"
fi
[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "expected SHA must be a full lowercase Git SHA" >&2; exit 14; }
repo_head="$(git -C "$STAGING_REPO" rev-parse --verify HEAD 2>/dev/null)" || {
  echo "Apply staging repository has no verifiable HEAD" >&2
  exit 15
}
[[ "$repo_head" == "$EXPECTED_SHA" ]] || {
  echo "Apply staging checkout/image provenance mismatch: checkout=$repo_head expected=$EXPECTED_SHA" >&2
  exit 16
}

echo "APPLY_STAGING_SOURCE_PROVENANCE=PASS"

compose=(
  docker compose
  --project-name "$PROJECT"
  --env-file "$STAGING_ENV"
  -f "$STAGING_REPO/deploy/staging/compose.yaml"
)

rendered="$(mktemp /tmp/munshi-apply-${target}-rendered.XXXXXX.json)"
trap 'rm -f "$rendered"' EXIT

env \
  MUNSHI_APPLY_DEPLOY_SHA="$EXPECTED_SHA" \
  MUNSHI_APPLY_IMAGE_TAG="$EXPECTED_SHA" \
  "${compose[@]}" --profile hosted-prepare --profile hosted-submit-proof config -q

env \
  MUNSHI_APPLY_DEPLOY_SHA="$EXPECTED_SHA" \
  MUNSHI_APPLY_IMAGE_TAG="$EXPECTED_SHA" \
  "${compose[@]}" --profile hosted-prepare --profile hosted-submit-proof config --format json > "$rendered"

python3 - "$rendered" "$BIND_HOST" "$PUBLISHED_PORT" "$HUNTER_NETWORK" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_bind_host, expected_port, expected_network = sys.argv[2:5]
services = config.get("services", {})
required = {"apply", "prepare-worker", "submit-worker"}
missing = sorted(required - services.keys())
if missing:
    raise SystemExit(f"missing Apply staging services: {missing}")

apply = services["apply"]
apply_env = apply.get("environment", {})
for key in ("MUNSHI_FINAL_REVIEW_ENABLED", "MUNSHI_FINAL_SUBMIT_ENABLED"):
    if str(apply_env.get(key, "")).lower() != "false":
        raise SystemExit(f"normal Apply service must force {key}=false")

ports = apply.get("ports", [])
if len(ports) != 1:
    raise SystemExit(f"Apply staging must expose exactly one port: {ports!r}")
port = ports[0]
if str(port.get("target")) != "8000" or str(port.get("published")) != expected_port:
    raise SystemExit(f"unexpected Apply staging port mapping: {port!r}")
if port.get("host_ip") != expected_bind_host:
    raise SystemExit(f"Apply staging port must bind loopback only: {port!r}")

submit = services["submit-worker"]
if "hosted-submit-proof" not in submit.get("profiles", []):
    raise SystemExit("submit-worker must remain behind hosted-submit-proof profile")
submit_env = submit.get("environment", {})
for key in (
    "MUNSHI_APPLY_HOSTED_SUBMIT_WORKER_ENABLED",
    "MUNSHI_FINAL_REVIEW_ENABLED",
    "MUNSHI_FINAL_SUBMIT_ENABLED",
    "MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED",
):
    if str(submit_env.get(key, "")).lower() != "false":
        raise SystemExit(f"submit proof gate must default false: {key}")

networks = config.get("networks", {})
hunter = networks.get("hunter_internal", {})
if hunter.get("name") != expected_network:
    raise SystemExit("Apply staging must attach only to the established Hunter staging application network")

print("APPLY_STAGING_COMPOSE_SAFETY=PASS")
PY

submit_ids="$(docker ps -q \
  --filter "label=com.docker.compose.project=$PROJECT" \
  --filter 'label=com.docker.compose.service=submit-worker')"
[[ -z "$submit_ids" ]] || {
  echo "Apply submit-worker is active during normal staging verification" >&2
  exit 20
}
echo "APPLY_STAGING_SUBMIT_WORKER_ACTIVE=NO"

mapfile -t apply_ids < <(docker ps -q \
  --filter "label=com.docker.compose.project=$PROJECT" \
  --filter 'label=com.docker.compose.service=apply')
[[ "${#apply_ids[@]}" -eq 1 ]] || {
  echo "expected exactly one running Apply staging API container; found ${#apply_ids[@]}" >&2
  exit 21
}
apply_id="${apply_ids[0]}"

health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$apply_id")"
[[ "$health" == "healthy" ]] || { echo "Apply staging API is not healthy: $health" >&2; exit 22; }

revision="$(docker inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$apply_id")"
[[ "$revision" == "$EXPECTED_SHA" ]] || {
  echo "running Apply image revision mismatch: expected=$EXPECTED_SHA actual=$revision" >&2
  exit 23
}

container_env="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$apply_id")"
grep -qx 'MUNSHI_FINAL_REVIEW_ENABLED=false' <<<"$container_env" || { echo "running Apply final-review gate is not false" >&2; exit 24; }
grep -qx 'MUNSHI_FINAL_SUBMIT_ENABLED=false' <<<"$container_env" || { echo "running Apply final-submit gate is not false" >&2; exit 25; }

port_binding="$(docker port "$apply_id" 8000/tcp)"
[[ "$port_binding" == "$BIND_HOST:$PUBLISHED_PORT" ]] || {
  echo "Apply deployment port mismatch: expected=$BIND_HOST:$PUBLISHED_PORT actual=$port_binding" >&2
  exit 26
}

docker inspect -f '{{json .NetworkSettings.Networks}}' "$apply_id" \
  | grep -Fq "$HUNTER_NETWORK" || {
    echo "Apply staging is not attached to the Hunter staging application network" >&2
    exit 27
  }

python3 - "$BIND_HOST" "$PUBLISHED_PORT" <<'PY'
import sys
import urllib.request
with urllib.request.urlopen(f"http://{sys.argv[1]}:{sys.argv[2]}/health", timeout=5) as response:
    if response.status != 200:
        raise SystemExit(f"Apply staging /health returned {response.status}")
print("APPLY_STAGING_HTTP_HEALTH=PASS")
PY

docker exec "$apply_id" python /app/scripts/runtime-ops.py health \
  --database /data/munshi-apply.sqlite \
  --migrations /app/migrations >/dev/null

echo "APPLY_STAGING_DATABASE_HEALTH=PASS"
echo "APPLY_STAGING_IMAGE_REVISION=$revision"
echo "APPLY_STAGING_FINAL_SUBMIT_ENABLED=false"
echo "RESULT=APPLY_STAGING_RUNTIME_CONTRACT_PASS"

#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="${MUNSHI_APPLY_PRODUCTION_ROOT:-/opt/munshi/apply-production}"
REPO="$ROOT/repo"
ENV_FILE="${MUNSHI_APPLY_PRODUCTION_ENV_FILE:-$ROOT/runtime/production.env}"
PROJECT="${MUNSHI_APPLY_PRODUCTION_PROJECT:-munshi-apply-production}"
VERIFY="${MUNSHI_APPLY_PRODUCTION_VERIFY:-/opt/munshi/bin/verify-apply-production-runtime-contract}"
EXPECTED_SHA=""

while (($#)); do
  case "$1" in
    --expected-sha) EXPECTED_SHA="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -d "$REPO/.git" ]] || { echo "Apply production repo missing" >&2; exit 10; }
[[ -f "$ENV_FILE" ]] || { echo "Apply production env missing" >&2; exit 11; }
if [[ -z "$EXPECTED_SHA" ]]; then EXPECTED_SHA="$(git -c "safe.directory=$REPO" -C "$REPO" rev-parse HEAD)"; fi
[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "expected SHA invalid" >&2; exit 12; }
[[ "$(git -c "safe.directory=$REPO" -C "$REPO" rev-parse HEAD)" == "$EXPECTED_SHA" ]] || { echo "Apply production SHA mismatch" >&2; exit 13; }

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
: "${MUNSHI_APPLY_IMAGE_REPOSITORY:=munshi-apply-production}"
: "${MUNSHI_HUNTER_NETWORK_NAME:=munshi-netcup-shadow_application}"

compose=(
  docker compose
  --project-name "$PROJECT"
  --env-file "$ENV_FILE"
  -f "$REPO/deploy/production/compose.yaml"
)

"$VERIFY" --expected-sha "$EXPECTED_SHA" --expect-submit off

api_id="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=apply' | head -n1)"
prepare_id="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=prepare-worker' | head -n1)"
[[ -n "$api_id" && -n "$prepare_id" ]] || { echo "Apply production reversible services missing" >&2; exit 14; }

for id in "$api_id" "$prepare_id"; do
  docker exec -i "$id" python - <<'PY'
import urllib.request
with urllib.request.urlopen("http://hunter:8000/health", timeout=5) as response:
    if response.status != 200:
        raise SystemExit(response.status)
print("HUNTER_PRIVATE_BRIDGE_HTTP_HEALTH=PASS")
PY
done

env_backup="$ENV_FILE.pre-full-submit"
cp -a "$ENV_FILE" "$env_backup"

set_env_value() {
  local key="$1" value="$2" file="$3"
  python3 - "$key" "$value" "$file" <<'PY'
import os,sys,tempfile
key,value,path=sys.argv[1:]
with open(path,"r",encoding="utf-8") as fh: lines=fh.readlines()
out=[]; found=False
for line in lines:
    if line.startswith(key+"="):
        out.append(f"{key}={value}\n"); found=True
    else:
        out.append(line)
if not found: out.append(f"{key}={value}\n")
d=os.path.dirname(path) or "."
fd,tmp=tempfile.mkstemp(prefix=".env.",dir=d,text=True)
try:
    with os.fdopen(fd,"w",encoding="utf-8") as fh: fh.writelines(out)
    st=os.stat(path)
    os.chown(tmp,st.st_uid,st.st_gid); os.chmod(tmp,st.st_mode & 0o777)
    os.replace(tmp,path)
except Exception:
    try: os.unlink(tmp)
    except FileNotFoundError: pass
    raise
PY
}

rollback_activation() {
  rc=$?
  trap - ERR
  echo "=== ROLLBACK APPLY FULL-SUBMIT ACTIVATION rc=$rc ===" >&2
  cp -a "$env_backup" "$ENV_FILE" || true
  set -a; source "$ENV_FILE"; set +a
  MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED=false   MUNSHI_APPLY_DEPLOY_SHA="$EXPECTED_SHA" MUNSHI_APPLY_IMAGE_TAG="$EXPECTED_SHA"     "${compose[@]}" --profile hosted-prepare --profile hosted-submit rm -sf submit-worker >/dev/null 2>&1 || true
  MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED=false   MUNSHI_APPLY_DEPLOY_SHA="$EXPECTED_SHA" MUNSHI_APPLY_IMAGE_TAG="$EXPECTED_SHA"     "${compose[@]}" --profile hosted-prepare up -d --no-deps --force-recreate apply || true
  echo "APPLY_FINAL_SUBMIT_RUNTIME=DISABLED_AFTER_ROLLBACK" >&2
  exit "$rc"
}
trap rollback_activation ERR

set_env_value MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED true "$ENV_FILE"

set -a
source "$ENV_FILE"
set +a

echo "=== ENABLE APPLY AUTHORITY INGEST ==="
MUNSHI_APPLY_DEPLOY_SHA="$EXPECTED_SHA" MUNSHI_APPLY_IMAGE_TAG="$EXPECTED_SHA"   "${compose[@]}" --profile hosted-prepare up -d --no-deps --force-recreate apply

for _ in $(seq 1 60); do
  api_id="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=apply' | head -n1)"
  [[ -n "$api_id" ]] || { sleep 2; continue; }
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$api_id" 2>/dev/null || true)"
  [[ "$health" == "healthy" ]] && break
  sleep 2
done
[[ "${health:-}" == "healthy" ]] || { echo "Apply API unhealthy after authority activation" >&2; exit 20; }

echo "=== START DEDICATED PRODUCTION SUBMIT WORKER ==="
MUNSHI_APPLY_DEPLOY_SHA="$EXPECTED_SHA" MUNSHI_APPLY_IMAGE_TAG="$EXPECTED_SHA"   "${compose[@]}" --profile hosted-prepare --profile hosted-submit up -d submit-worker

for _ in $(seq 1 30); do
  submit_id="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=submit-worker' | head -n1)"
  [[ -n "$submit_id" ]] && break
  sleep 2
done
[[ -n "${submit_id:-}" ]] || { echo "Apply production submit worker did not start" >&2; exit 21; }

# The worker should be alive and idle; no application is synthesized by deployment.
sleep 3
running="$(docker inspect -f '{{.State.Running}}' "$submit_id")"
oom="$(docker inspect -f '{{.State.OOMKilled}}' "$submit_id")"
[[ "$running" == "true" && "$oom" == "false" ]] || { echo "Apply submit worker exited during activation" >&2; exit 22; }

"$VERIFY" --expected-sha "$EXPECTED_SHA" --expect-submit on

rm -f "$env_backup"
trap - ERR
echo "APPLY_PRODUCTION_AUTHORITY_INGEST=ENABLED"
echo "APPLY_PRODUCTION_HOSTED_SUBMIT_WORKER=ENABLED"
echo "APPLY_PRODUCTION_FINAL_SUBMIT=ENABLED"
echo "RESULT=APPLY_PRODUCTION_FULL_SUBMIT_ACTIVATION_PASS"
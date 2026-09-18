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
PROTECTED_COMPOSE_PROJECTS=""
PROTECTED_CONTAINER_NAMES=""

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
  PROTECTED_COMPOSE_PROJECTS="$(target_value MUNSHI_APPLY_PROTECTED_COMPOSE_PROJECTS)"
  PROTECTED_CONTAINER_NAMES="$(target_value MUNSHI_APPLY_PROTECTED_CONTAINER_NAMES)"

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
  [[ "$PROTECTED_COMPOSE_PROJECTS" == "NONE" || "$PROTECTED_COMPOSE_PROJECTS" =~ ^[A-Za-z0-9_.-]+(,[A-Za-z0-9_.-]+)*$ ]] || { echo "invalid MUNSHI_APPLY_PROTECTED_COMPOSE_PROJECTS" >&2; exit 7; }
  [[ "$PROTECTED_CONTAINER_NAMES" == "NONE" || "$PROTECTED_CONTAINER_NAMES" =~ ^[A-Za-z0-9_.-]+(,[A-Za-z0-9_.-]+)*$ ]] || { echo "invalid MUNSHI_APPLY_PROTECTED_CONTAINER_NAMES" >&2; exit 7; }

  STAGING_REPO="$STAGING_ROOT/repo"
  STAGING_ENV="$RUNTIME_ENV_FILE"

  export MUNSHI_APPLY_COMPOSE_PROJECT="$PROJECT"
  export MUNSHI_APPLY_BIND_HOST="$BIND_HOST"
  export MUNSHI_APPLY_PUBLISHED_PORT="$PUBLISHED_PORT"
  export MUNSHI_HUNTER_NETWORK_NAME="$HUNTER_NETWORK"
  export MUNSHI_APPLY_IMAGE_REPOSITORY="$IMAGE_REPOSITORY"
  export MUNSHI_ENVIRONMENT="$DEPLOY_ENVIRONMENT"
}
VERIFY="/opt/munshi/bin/verify-apply-staging-runtime-contract"
LOCK_FILE=""

commit=""
branch=""
bundle_file=""
deploy_ref=""
rendered=""
recreated=0
had_old_head=0
had_old_container=0
old_head=""
old_branch=""
old_apply_id=""
old_image_id=""
old_image_ref=""
old_revision=""
rollback_tag=""
db_backup="NONE_FIRST_DEPLOY"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"



cleanup() {
  [[ -n "${bundle_file:-}" ]] && rm -f "$bundle_file" 2>/dev/null || true
  [[ -n "${rendered:-}" ]] && rm -f "$rendered" 2>/dev/null || true
  if [[ -n "${deploy_ref:-}" && -d "$STAGING_REPO/.git" ]]; then
    git -C "$STAGING_REPO" update-ref -d "$deploy_ref" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

while (($#)); do
  case "$1" in
    --target) target="${2:-}"; shift 2 ;;
    --commit) commit="${2:-}"; shift 2 ;;
    --branch) branch="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

load_target_config
LOCK_FILE="$STAGING_ROOT/runtime/deploy.lock"

[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo "--commit must be a full lowercase Git SHA" >&2; exit 3; }
[[ "$branch" =~ ^[A-Za-z0-9._/-]+$ ]] || { echo "--branch invalid" >&2; exit 4; }
git check-ref-format --branch "$branch" >/dev/null || { echo "--branch is not a valid Git branch name" >&2; exit 4; }
[[ -x "$VERIFY" ]] || { echo "Apply staging verifier missing: $VERIFY" >&2; exit 5; }
[[ -d "$STAGING_REPO/.git" ]] || { echo "Apply staging repository missing: $STAGING_REPO" >&2; exit 6; }
[[ -f "$STAGING_ENV" ]] || { echo "Apply staging env file missing: $STAGING_ENV" >&2; exit 7; }
docker network inspect "$HUNTER_NETWORK" >/dev/null 2>&1 || { echo "Hunter staging application network missing: $HUNTER_NETWORK" >&2; exit 8; }

mkdir -p "$STAGING_ROOT/runtime" "$STAGING_ROOT/backups" "$STAGING_ROOT/receipts"
chmod 700 "$STAGING_ROOT/runtime" "$STAGING_ROOT/backups" "$STAGING_ROOT/receipts"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "another Apply staging deployment is already running" >&2; exit 9; }

bundle_file="$(mktemp /tmp/munshi-apply-${target}-deploy.XXXXXX.bundle)"
timeout 120s cat > "$bundle_file" || { echo "Apply staging deployment bundle transfer timed out" >&2; exit 10; }
[[ -s "$bundle_file" ]] || { echo "Apply staging deployment bundle is empty" >&2; exit 11; }

cd "$STAGING_REPO"
[[ -z "$(git status --porcelain)" ]] || { echo "dirty Apply staging repository; refusing deployment" >&2; exit 12; }

if old_head="$(git rev-parse --verify HEAD 2>/dev/null)"; then
  had_old_head=1
  old_branch="$(git branch --show-current)"
fi

mapfile -t apply_containers < <(docker ps -aq \
  --filter "label=com.docker.compose.project=$PROJECT" \
  --filter 'label=com.docker.compose.service=apply')
[[ "${#apply_containers[@]}" -le 1 ]] || { echo "multiple Apply staging API containers found" >&2; exit 13; }
if [[ "${#apply_containers[@]}" -eq 1 ]]; then
  old_apply_id="${apply_containers[0]}"
  running="$(docker inspect -f '{{.State.Running}}' "$old_apply_id")"
  [[ "$running" == "true" ]] || { echo "existing Apply staging API container is not running" >&2; exit 14; }
  had_old_container=1
  old_image_id="$(docker inspect -f '{{.Image}}' "$old_apply_id")"
  old_image_ref="$(docker inspect -f '{{.Config.Image}}' "$old_apply_id")"
  old_revision="$(docker inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$old_apply_id")"
  [[ "$old_revision" =~ ^[0-9a-f]{40}$ ]] || { echo "existing Apply staging image lacks exact revision label" >&2; exit 15; }
  if (( had_old_head )); then
    [[ "$old_head" == "$old_revision" ]] || {
      echo "existing Apply target checkout/image provenance mismatch: checkout=$old_head image=$old_revision" >&2
      exit 16
    }
  fi
  old_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$old_apply_id")"
  [[ "$old_health" == "healthy" || "$old_health" == "running" ]] || {
    echo "existing Apply target container is not healthy: $old_health" >&2
    exit 16
  }
  echo "APPLY_EXISTING_TARGET_PREFLIGHT=PASS"
fi

for service in prepare-worker submit-worker; do
  active="$(docker ps -q \
    --filter "label=com.docker.compose.project=$PROJECT" \
    --filter "label=com.docker.compose.service=$service")"
  [[ -z "$active" ]] || {
    echo "$service is active; normal staging deployment requires preparation/submission proof workers to be stopped" >&2
    exit 17
  }
done

snapshot_hunter() {
  if [[ "$PROTECTED_COMPOSE_PROJECTS" != "NONE" ]]; then
    IFS=',' read -r -a protected_projects <<< "$PROTECTED_COMPOSE_PROJECTS"
    for project in "${protected_projects[@]}"; do
      while IFS= read -r id; do
        [[ -n "$id" ]] || continue
        docker inspect -f '{{.Id}}|{{.Name}}|{{.State.StartedAt}}|{{.RestartCount}}' "$id"
      done < <(docker ps -aq --filter "label=com.docker.compose.project=$project" | sort)
    done
  fi
  if [[ "$PROTECTED_CONTAINER_NAMES" != "NONE" ]]; then
    IFS=',' read -r -a protected_containers <<< "$PROTECTED_CONTAINER_NAMES"
    for protected_name in "${protected_containers[@]}"; do
      if docker inspect "$protected_name" >/dev/null 2>&1; then
        docker inspect -f '{{.Id}}|{{.Name}}|{{.State.StartedAt}}|{{.RestartCount}}' "$protected_name"
      fi
    done
  fi
}

hunter_snapshot_before="$(snapshot_hunter)"

if (( had_old_container )); then
  backup_dir="$STAGING_ROOT/backups"
  db_backup="$backup_dir/apply-predeploy-$stamp.sqlite"
  docker exec -i "$old_apply_id" python - "$stamp" <<'PY'
import sqlite3
import sys
from pathlib import Path

stamp = sys.argv[1]
src = Path("/data/munshi-apply.sqlite")
dst = Path("/tmp") / f"apply-predeploy-{stamp}.sqlite"
if not src.is_file():
    raise SystemExit(f"Apply staging database is missing: {src}")
source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
dest = sqlite3.connect(dst)
try:
    source.backup(dest)
    result = dest.execute("PRAGMA quick_check").fetchone()[0]
finally:
    dest.close()
    source.close()
if result != "ok":
    raise SystemExit(f"Apply staging backup quick_check failed: {result}")
print(dst)
PY
  docker cp "$old_apply_id:/tmp/apply-predeploy-$stamp.sqlite" "$db_backup"
  docker exec "$old_apply_id" rm -f "/tmp/apply-predeploy-$stamp.sqlite"
  chmod 600 "$db_backup"
  python3 - "$db_backup" <<'PY'
import sqlite3
import sys
path = sys.argv[1]
connection = sqlite3.connect(path)
try:
    result = connection.execute("PRAGMA quick_check").fetchone()[0]
finally:
    connection.close()
if result != "ok":
    raise SystemExit(f"host Apply staging backup quick_check failed: {result}")
print("APPLY_STAGING_DB_BACKUP_QUICK_CHECK=PASS")
PY
  rollback_tag="$IMAGE_REPOSITORY:rollback-$stamp"
  docker tag "$old_image_id" "$rollback_tag"
fi

git bundle verify "$bundle_file"

# Authenticated bundle producers may encode the selected branch either as a
# local branch ref (refs/heads/...) or a remote-tracking ref
# (refs/remotes/origin/...). Accept only those two exact representations of
# the requested branch; never guess or fetch an unrelated ref.
bundle_ref=""
for candidate in "refs/heads/$branch" "refs/remotes/origin/$branch"; do
  listed="$(git bundle list-heads "$bundle_file" "$candidate" || true)"
  listed_sha="${listed%% *}"
  listed_ref="${listed#* }"
  if [[ "$listed_sha" =~ ^[0-9a-f]{40}$ && "$listed_ref" == "$candidate" ]]; then
    bundle_ref="$candidate"
    break
  fi
done
[[ -n "$bundle_ref" ]] || {
  echo "deployment bundle does not contain requested branch: $branch" >&2
  git bundle list-heads "$bundle_file" >&2 || true
  exit 19
}

deploy_ref="refs/remotes/github-apply-deploy/$target/$branch"
git fetch --no-tags "$bundle_file" "+$bundle_ref:$deploy_ref"
git cat-file -e "$commit^{commit}"
git merge-base --is-ancestor "$commit" "$deploy_ref" || {
  echo "requested SHA is not contained in bundled Apply source branch" >&2
  exit 20
}
echo "APPLY_BUNDLE_SOURCE_REF=$bundle_ref"
echo "GITHUB_APPLY_STAGING_BUNDLE_IMPORT=PASS"

write_receipt() {
  local result="$1"
  local active_sha="$2"
  local receipt="$STAGING_ROOT/receipts/apply-$target-$stamp-$commit.json"
  python3 - "$receipt" "$result" "$commit" "$branch" "$active_sha" "${old_head:-}" "${rollback_tag:-}" "$db_backup" "$DEPLOY_ENVIRONMENT" "$target" <<'PY'
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

receipt, result, requested_sha, branch, active_sha, previous_sha, rollback_image, db_backup, environment, target = sys.argv[1:]
payload = {
    "schema_version": "1.0",
    "created_at": datetime.now(UTC).isoformat(),
    "environment": environment,
    "deployment_target": target,
    "component": "munshi-apply",
    "result": result,
    "requested_sha": requested_sha,
    "source_branch": branch,
    "active_sha": active_sha or None,
    "previous_sha": previous_sha or None,
    "rollback_image": rollback_image or None,
    "database_backup": None if db_backup == "NONE_FIRST_DEPLOY" else db_backup,
    "production_deployment_performed": False,
    "hunter_containers_recreated": False,
    "final_submit_enabled": False,
}
Path(receipt).write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY
  chmod 600 "$receipt"
  receipt_sha="$(sha256sum "$receipt" | awk '{print $1}')"
  echo "DEPLOYMENT_RECEIPT=$receipt"
  echo "DEPLOYMENT_RECEIPT_SHA256=$receipt_sha"
}

compose=(
  docker compose
  --project-name "$PROJECT"
  --env-file "$STAGING_ENV"
  -f "$STAGING_REPO/deploy/staging/compose.yaml"
)

rollback() {
  rc=$?
  trap - ERR
  echo "=== AUTOMATIC APPLY STAGING ROLLBACK rc=$rc ===" >&2

  if (( had_old_head )); then
    if [[ -n "$old_branch" ]]; then
      git checkout -q -B "$old_branch" "$old_head" || true
    else
      git checkout -q --detach "$old_head" || true
    fi
  fi

  if (( recreated )); then
    if (( had_old_container )); then
      docker tag "$old_image_id" "$rollback_tag" || true
      env \
        MUNSHI_APPLY_DEPLOY_SHA="$old_revision" \
        MUNSHI_APPLY_IMAGE_TAG="rollback-$stamp" \
        "${compose[@]}" up -d --no-deps --force-recreate apply || true
      for _ in $(seq 1 48); do
        current_id="$(docker ps -q \
          --filter "label=com.docker.compose.project=$PROJECT" \
          --filter 'label=com.docker.compose.service=apply' | head -n1)"
        [[ -n "$current_id" ]] || { sleep 5; continue; }
        health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$current_id" 2>/dev/null || true)"
        [[ "$health" == "healthy" ]] && break
        sleep 5
      done
      "$VERIFY" --target "$target" --expected-sha "$old_revision" || true
    else
      env \
        MUNSHI_APPLY_DEPLOY_SHA="$commit" \
        MUNSHI_APPLY_IMAGE_TAG="$commit" \
        "${compose[@]}" rm -sf apply || true
    fi
  fi

  hunter_snapshot_after="$(snapshot_hunter)"
  if [[ "$hunter_snapshot_before" != "$hunter_snapshot_after" ]]; then
    echo "WARNING: Hunter container identity snapshot changed during failed Apply deployment" >&2
  fi
  write_receipt "ROLLED_BACK" "${old_revision:-}" || true
  echo "RESULT=APPLY_STAGING_DEPLOYMENT_ROLLED_BACK" >&2
  exit "$rc"
}
trap rollback ERR

echo "=== CHECKOUT EXACT APPLY STAGING SHA ==="
git checkout -q -B "$branch" "$commit"
[[ "$(git rev-parse HEAD)" == "$commit" ]]
[[ "$(git branch --show-current)" == "$branch" ]]
[[ -z "$(git status --porcelain)" ]]

echo "=== STATIC APPLY STAGING VALIDATION ==="
bash -n deploy/netcup/deploy_apply_staging_release.sh
bash -n deploy/netcup/verify_apply_staging_runtime_contract.sh
bash -n deploy/netcup/github_apply_staging_deploy_gateway.sh
python3 -m compileall -q apps/native-host/src scripts

rendered="$(mktemp /tmp/munshi-apply-${target}-rendered.XXXXXX.json)"
env \
  MUNSHI_APPLY_DEPLOY_SHA="$commit" \
  MUNSHI_APPLY_IMAGE_TAG="$commit" \
  "${compose[@]}" --profile hosted-prepare --profile hosted-submit-proof config -q
env \
  MUNSHI_APPLY_DEPLOY_SHA="$commit" \
  MUNSHI_APPLY_IMAGE_TAG="$commit" \
  "${compose[@]}" --profile hosted-prepare --profile hosted-submit-proof config --format json > "$rendered"
python3 - "$rendered" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
services = config["services"]
apply_env = services["apply"].get("environment", {})
for key in ("MUNSHI_FINAL_REVIEW_ENABLED", "MUNSHI_FINAL_SUBMIT_ENABLED"):
    if str(apply_env.get(key, "")).lower() != "false":
        raise SystemExit(f"unsafe normal Apply staging gate: {key}")
submit = services["submit-worker"]
if "hosted-submit-proof" not in submit.get("profiles", []):
    raise SystemExit("submit-worker lost hosted-submit-proof profile")
print("APPLY_STAGING_PREDEPLOY_CONFIG_SAFETY=PASS")
PY
rm -f "$rendered"
rendered=""

echo "=== BUILD EXACT-SHA APPLY STAGING IMAGE ==="
env \
  MUNSHI_APPLY_DEPLOY_SHA="$commit" \
  MUNSHI_APPLY_IMAGE_TAG="$commit" \
  "${compose[@]}" build apply
new_image_id="$(docker image inspect -f '{{.Id}}' "$IMAGE_REPOSITORY:$commit")"
new_revision="$(docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$IMAGE_REPOSITORY:$commit")"
[[ "$new_revision" == "$commit" ]] || { echo "built Apply image revision mismatch" >&2; exit 30; }

echo "=== RECREATE APPLY STAGING API ONLY ==="
env \
  MUNSHI_APPLY_DEPLOY_SHA="$commit" \
  MUNSHI_APPLY_IMAGE_TAG="$commit" \
  "${compose[@]}" up -d --no-deps --force-recreate apply
recreated=1

healthy=0
for _ in $(seq 1 48); do
  current_id="$(docker ps -q \
    --filter "label=com.docker.compose.project=$PROJECT" \
    --filter 'label=com.docker.compose.service=apply' | head -n1)"
  [[ -n "$current_id" ]] || { sleep 5; continue; }
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$current_id" 2>/dev/null || true)"
  if [[ "$health" == "healthy" ]]; then
    healthy=1
    break
  fi
  sleep 5
done
[[ "$healthy" == "1" ]] || { echo "Apply staging API did not return healthy" >&2; exit 31; }

"$VERIFY" --target "$target" --expected-sha "$commit"

hunter_snapshot_after="$(snapshot_hunter)"
[[ "$hunter_snapshot_before" == "$hunter_snapshot_after" ]] || {
  echo "Hunter staging/production container identity changed during Apply-only deployment" >&2
  exit 32
}
echo "HUNTER_STAGING_CONTAINERS_RECREATED=NO"
echo "HUNTER_PRODUCTION_CONTAINERS_RECREATED=NO"

write_receipt "PASS" "$commit"
echo "DEPLOYED_TARGET=$target"
echo "DEPLOYED_SHA=$commit"
echo "DEPLOYED_BRANCH=$branch"
echo "PREVIOUS_APPLY_STAGING_SHA=${old_head:-NONE}"
echo "DEPLOYED_IMAGE_ID=$new_image_id"
echo "ROLLBACK_IMAGE=${rollback_tag:-NONE_FIRST_DEPLOY}"
echo "STAGING_DB_BACKUP=$db_backup"
echo "PRODUCTION_DEPLOYMENT_PERFORMED=NO"
echo "FINAL_SUBMIT_ENABLED=false"
echo "RESULT=APPLY_STAGING_DEPLOYMENT_PASS"
trap - ERR

#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="${MUNSHI_APPLY_PRODUCTION_ROOT:-/opt/munshi/apply-production}"
REPO="$ROOT/repo"
ENV_FILE="${MUNSHI_APPLY_PRODUCTION_ENV_FILE:-$ROOT/runtime/production.env}"
PROJECT="${MUNSHI_APPLY_PRODUCTION_PROJECT:-munshi-apply-production}"
VERIFY="${MUNSHI_APPLY_PRODUCTION_VERIFY:-/opt/munshi/bin/verify-apply-production-runtime-contract}"

commit=""
branch=""
bundle_file=""
deploy_ref=""
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
old_head=""
old_branch=""
old_api_id=""
old_image_id=""
old_image_ref=""
old_revision=""
old_submit_running=0
db_backup="NONE_FIRST_DEPLOY"
recreated=0

cleanup() {
  [[ -n "${bundle_file:-}" ]] && rm -f "$bundle_file" 2>/dev/null || true
  if [[ -n "${deploy_ref:-}" && -d "$REPO/.git" ]]; then
    git -C "$REPO" update-ref -d "$deploy_ref" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

while (($#)); do
  case "$1" in
    --commit) commit="${2:-}"; shift 2 ;;
    --branch) branch="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo "--commit must be full lowercase SHA" >&2; exit 3; }
git check-ref-format --branch "$branch" >/dev/null || { echo "--branch invalid" >&2; exit 4; }
[[ -x "$VERIFY" ]] || { echo "Apply production verifier missing: $VERIFY" >&2; exit 5; }
[[ -f "$ENV_FILE" ]] || { echo "Apply production env file missing: $ENV_FILE" >&2; exit 6; }

mkdir -p "$ROOT" "$ROOT/runtime" "$ROOT/backups" "$ROOT/receipts" "$REPO"
chmod 700 "$ROOT/runtime" "$ROOT/backups" "$ROOT/receipts"
# SSH/runuser can inherit /root, which the deployment user cannot stat.
# Compose resolves its schema and project paths relative to the process cwd.
cd -- "$REPO"
if [[ ! -d "$REPO/.git" ]]; then
  if find "$REPO" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
    echo "Apply production repo directory non-empty but not Git" >&2; exit 7
  fi
  git -C "$REPO" init -q
fi
[[ -z "$(git -C "$REPO" status --porcelain)" ]] || { echo "Apply production repo dirty" >&2; exit 8; }

bundle_file="$(mktemp /tmp/munshi-apply-production.XXXXXX.bundle)"
timeout 120s cat > "$bundle_file"
[[ -s "$bundle_file" ]] || { echo "Apply production bundle empty" >&2; exit 9; }

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
  [[ "${#value}" -ge 32 ]] || { echo "required production secret missing/too short: $key" >&2; exit 10; }
done
docker network inspect "$MUNSHI_HUNTER_NETWORK_NAME" >/dev/null 2>&1 || {
  echo "Hunter production network missing: $MUNSHI_HUNTER_NETWORK_NAME" >&2; exit 11;
}

compose=(
  docker compose
  --project-name "$PROJECT"
  --env-file "$ENV_FILE"
  -f "$REPO/deploy/production/compose.yaml"
)

snapshot_protected() {
  for name in     munshi-netcup-shadow-hunter-1     munshi-netcup-shadow-n8n-1     munshi-netcup-shadow-ollama-1     munshi-apply-staging-apply-1     munshi-apply-staging-prepare-worker-1     munshi-apply-staging-submit-worker-1
  do
    if docker inspect "$name" >/dev/null 2>&1; then
      docker inspect -f '{{.Id}}|{{.Name}}|{{.State.StartedAt}}|{{.RestartCount}}' "$name"
    fi
  done
}
protected_before="$(snapshot_protected)"

if old_head="$(git -C "$REPO" rev-parse --verify HEAD 2>/dev/null)"; then
  old_branch="$(git -C "$REPO" branch --show-current)"
fi

old_api_id="$(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=apply' | head -n1)"
old_submit_id="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=submit-worker' | head -n1)"
[[ -z "$old_submit_id" ]] || old_submit_running=1

backup_apply_db() {
  [[ -n "$old_api_id" ]] || return 0
  old_image_id="$(docker inspect -f '{{.Image}}' "$old_api_id")"
  old_image_ref="$(docker inspect -f '{{.Config.Image}}' "$old_api_id")"
  old_revision="$(docker inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$old_api_id")"
  [[ "$old_revision" =~ ^[0-9a-f]{40}$ ]] || { echo "existing Apply production image lacks revision" >&2; exit 12; }

  active_submitting="$(docker exec -i "$old_api_id" python - <<'PY'
import sqlite3
p="/data/munshi-apply.sqlite"
db=sqlite3.connect(f"file:{p}?mode=ro",uri=True,timeout=30)
db.execute("PRAGMA query_only=ON")
try:
    n=db.execute("SELECT COUNT(*) FROM complete_application_sessions WHERE state='SUBMITTING'").fetchone()[0]
except sqlite3.OperationalError:
    n=0
finally:
    db.close()
print(n)
PY
)"
  [[ "$active_submitting" == "0" ]] || { echo "Apply production has active SUBMITTING session(s): $active_submitting" >&2; exit 13; }

  db_backup="$ROOT/backups/apply-predeploy-$stamp.sqlite"
  docker exec -i "$old_api_id" python - "$stamp" <<'PY'
import sqlite3,sys
from pathlib import Path
stamp=sys.argv[1]
src=Path("/data/munshi-apply.sqlite")
dst=Path("/tmp")/f"apply-predeploy-{stamp}.sqlite"
source=sqlite3.connect(f"file:{src}?mode=ro",uri=True,timeout=30)
dest=sqlite3.connect(dst)
try:
    source.backup(dest)
    assert dest.execute("PRAGMA quick_check").fetchone()[0]=="ok"
finally:
    dest.close(); source.close()
print(dst)
PY
  docker cp "$old_api_id:/tmp/apply-predeploy-$stamp.sqlite" "$db_backup"
  docker exec -i "$old_api_id" rm -f "/tmp/apply-predeploy-$stamp.sqlite"
  chmod 600 "$db_backup"
  python3 - "$db_backup" <<'PY'
import sqlite3,sys
db=sqlite3.connect(sys.argv[1])
try:
    assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok"
finally: db.close()
print("APPLY_PRODUCTION_DB_BACKUP_QUICK_CHECK=PASS")
PY
}
backup_apply_db

restore_apply_db() {
  [[ "$db_backup" != "NONE_FIRST_DEPLOY" ]] || return 0
  volume="$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT" | head -n1)"
  if [[ -z "$volume" ]]; then
    volume="${PROJECT}_apply_data"
  fi
  docker run --rm -i --user 0:0     --network none     --mount "type=volume,src=$volume,dst=/data"     --mount "type=bind,src=$ROOT/backups,dst=/backup,readonly"     --entrypoint python     "$old_image_id" - "$(basename "$db_backup")" <<'PY'
import os,shutil,sqlite3,sys
from pathlib import Path
backup=Path("/backup")/sys.argv[1]
live=Path("/data/munshi-apply.sqlite")
tmp=Path("/data/munshi-apply.sqlite.rollback")
for p in (tmp,Path(str(live)+"-wal"),Path(str(live)+"-shm"),Path(str(live)+"-journal")):
    try:p.unlink()
    except FileNotFoundError:pass
shutil.copyfile(backup,tmp)
os.replace(tmp,live)
db=sqlite3.connect(f"file:{live}?mode=ro",uri=True,timeout=30)
try:
    assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok"
finally: db.close()
print("APPLY_PRODUCTION_ROLLBACK_DB_RESTORE=PASS")
PY
}

rollback() {
  rc=$?
  trap - ERR
  echo "=== AUTOMATIC APPLY PRODUCTION ROLLBACK rc=$rc ===" >&2
  if [[ -f "$REPO/deploy/production/compose.yaml" ]]; then
    MUNSHI_APPLY_DEPLOY_SHA="$commit" MUNSHI_APPLY_IMAGE_TAG="$commit"       "${compose[@]}" --profile hosted-prepare --profile hosted-submit rm -sf submit-worker prepare-worker apply >/dev/null 2>&1 || true
  fi
  if [[ -n "$old_head" ]]; then
    if [[ -n "$old_branch" ]]; then git -C "$REPO" checkout -q -B "$old_branch" "$old_head" || true
    else git -C "$REPO" checkout -q --detach "$old_head" || true; fi
    restore_apply_db || true
    if [[ -n "$old_image_id" && -n "$old_image_ref" ]]; then
      docker tag "$old_image_id" "$old_image_ref" || true
      old_tag="${old_image_ref##*:}"
      MUNSHI_APPLY_DEPLOY_SHA="$old_revision" MUNSHI_APPLY_IMAGE_TAG="$old_tag"         "${compose[@]}" --profile hosted-prepare up -d apply prepare-worker || true
      if (( old_submit_running )); then
        MUNSHI_APPLY_DEPLOY_SHA="$old_revision" MUNSHI_APPLY_IMAGE_TAG="$old_tag"           "${compose[@]}" --profile hosted-prepare --profile hosted-submit up -d submit-worker || true
      fi
    fi
  fi
  protected_after="$(snapshot_protected)"
  [[ "$protected_before" == "$protected_after" ]] || echo "WARNING: protected container identity changed during failed Apply deployment" >&2
  echo "RESULT=APPLY_PRODUCTION_DEPLOYMENT_ROLLED_BACK" >&2
  exit "$rc"
}
trap rollback ERR

echo "=== VERIFY APPLY PRODUCTION BUNDLE ==="
git -C "$REPO" bundle verify "$bundle_file"
bundle_ref=""
for candidate in "refs/heads/$branch" "refs/remotes/origin/$branch"; do
  line="$(git -C "$REPO" bundle list-heads "$bundle_file" "$candidate" || true)"
  sha="${line%% *}"
  ref="${line#* }"
  if [[ "$sha" =~ ^[0-9a-f]{40}$ && "$ref" == "$candidate" ]]; then bundle_ref="$candidate"; break; fi
done
[[ -n "$bundle_ref" ]] || { echo "requested Apply production branch absent from bundle" >&2; exit 20; }
deploy_ref="refs/remotes/github-apply-production/$branch"
git -C "$REPO" fetch --no-tags "$bundle_file" "+$bundle_ref:$deploy_ref"
git -C "$REPO" cat-file -e "$commit^{commit}"
git -C "$REPO" merge-base --is-ancestor "$commit" "$deploy_ref"
echo "APPLY_PRODUCTION_BUNDLE_IMPORT=PASS"

git -C "$REPO" checkout -q -B "$branch" "$commit"
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$commit" ]]
[[ -z "$(git -C "$REPO" status --porcelain)" ]]

bash -n "$REPO/deploy/netcup/deploy_apply_production_release.sh"
bash -n "$REPO/deploy/netcup/verify_apply_production_runtime_contract.sh"
python3 -m compileall -q "$REPO/apps/native-host/src" "$REPO/scripts"

MUNSHI_APPLY_DEPLOY_SHA="$commit" MUNSHI_APPLY_IMAGE_TAG="$commit"   "${compose[@]}" --profile hosted-prepare --profile hosted-submit config -q

echo "=== BUILD APPLY PRODUCTION IMAGE ==="
MUNSHI_APPLY_DEPLOY_SHA="$commit" MUNSHI_APPLY_IMAGE_TAG="$commit" "${compose[@]}" build apply
revision="$(docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$MUNSHI_APPLY_IMAGE_REPOSITORY:$commit")"
[[ "$revision" == "$commit" ]] || { echo "built Apply production image revision mismatch" >&2; exit 21; }

echo "=== RUN EXACT-IMAGE APPLY PRODUCTION REGRESSION SUITE (NETWORK DISABLED) ==="
timeout 1200s docker run --rm \
  --network none \
  --read-only \
  --tmpfs /data:rw,nosuid,nodev,size=256m,uid=10001,gid=10001,mode=0700 \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m \
  --tmpfs /home/munshiapply:rw,nosuid,nodev,size=128m \
  --entrypoint python \
  "$MUNSHI_APPLY_IMAGE_REPOSITORY:$commit" \
  -m pytest -q \
    /app/apps/native-host/tests/test_internal_http_policy.py \
    /app/apps/native-host/tests/test_production_deployment_contract.py \
    /app/apps/native-host/tests/test_hosted_submit_worker.py \
    /app/apps/native-host/tests/test_hosted_submit_worker_resilience.py \
    /app/apps/native-host/tests/test_production_submission_verification_determinism.py \
    /app/apps/native-host/tests/test_submit_authority_inbox.py \
    /app/apps/native-host/tests/test_submit_authority_contract_vector.py
echo "APPLY_PRODUCTION_EXACT_IMAGE_TESTS=PASS"

echo "=== FORCE SUBMIT OFF DURING REVERSIBLE DEPLOYMENT ==="
MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED=false MUNSHI_APPLY_DEPLOY_SHA="$commit" MUNSHI_APPLY_IMAGE_TAG="$commit"   "${compose[@]}" --profile hosted-prepare stop submit-worker >/dev/null 2>&1 || true
MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED=false MUNSHI_APPLY_DEPLOY_SHA="$commit" MUNSHI_APPLY_IMAGE_TAG="$commit"   "${compose[@]}" --profile hosted-prepare up -d --force-recreate apply prepare-worker
recreated=1

for _ in $(seq 1 60); do
  api_id="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter 'label=com.docker.compose.service=apply' | head -n1)"
  [[ -n "$api_id" ]] || { sleep 3; continue; }
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$api_id" 2>/dev/null || true)"
  [[ "$health" == "healthy" ]] && break
  sleep 3
done
[[ "${health:-}" == "healthy" ]] || { echo "Apply production API did not become healthy" >&2; exit 22; }

"$VERIFY" --expected-sha "$commit" --expect-submit off

protected_after="$(snapshot_protected)"
[[ "$protected_before" == "$protected_after" ]] || {
  echo "Protected Hunter/n8n/Ollama/staging container identity changed during Apply production deployment" >&2
  exit 23
}

echo "DEPLOYED_APPLY_PRODUCTION_SHA=$commit"
echo "DEPLOYED_APPLY_PRODUCTION_BRANCH=$branch"
echo "APPLY_PRODUCTION_DB_BACKUP=$db_backup"
echo "FINAL_SUBMIT_ENABLED=false"
echo "RESULT=APPLY_PRODUCTION_DEPLOYMENT_PASS"
trap - ERR

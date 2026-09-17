#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

BIN_ROOT="${MUNSHI_ROOT:-/opt/munshi}/bin"
STAGING_ROOT="${MUNSHI_APPLY_STAGING_ROOT:-/home/munshi/munshi-apply-staging-v1}"
STAGING_REPO="$STAGING_ROOT/repo"
STAGING_ENV="$STAGING_ROOT/staging.env"
TARGET_USER="${MUNSHI_DEPLOY_SSH_USER:-munshi}"
PUBLIC_KEY_FILE=""
SOURCE_ROOT="${MUNSHI_DEPLOY_SOURCE_ROOT:-}"
SOURCE_SHA="${MUNSHI_DEPLOY_SOURCE_SHA:-}"
KEY_COMMENT="munshi-github-actions-apply-staging-deploy"
HUNTER_NETWORK="munshi-netcup-staging_application"

while (($#)); do
  case "$1" in
    --public-key-file) PUBLIC_KEY_FILE="${2:-}"; shift 2 ;;
    --target-user) TARGET_USER="${2:-}"; shift 2 ;;
    --source-root) SOURCE_ROOT="${2:-}"; shift 2 ;;
    --source-sha) SOURCE_SHA="${2:-}"; shift 2 ;;
    -h|--help)
      echo "Usage: sudo $0 --public-key-file /path/to/apply-staging.pub --source-root /path/to/approved/apply-worktree --source-sha <40-char-sha> [--target-user munshi]"
      exit 0
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ "$EUID" -eq 0 ]] || { echo "run with sudo/root" >&2; exit 10; }
[[ -n "$PUBLIC_KEY_FILE" && -f "$PUBLIC_KEY_FILE" ]] || { echo "--public-key-file is required" >&2; exit 11; }
id "$TARGET_USER" >/dev/null 2>&1 || { echo "target user does not exist: $TARGET_USER" >&2; exit 12; }
[[ -n "$SOURCE_ROOT" && -d "$SOURCE_ROOT/.git" ]] || { echo "--source-root must be an approved Apply Git worktree" >&2; exit 13; }
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "--source-sha must be a full lowercase Git SHA" >&2; exit 14; }
[[ "$(git -C "$SOURCE_ROOT" rev-parse HEAD)" == "$SOURCE_SHA" ]] || { echo "approved Apply source SHA mismatch" >&2; exit 15; }
[[ -z "$(git -C "$SOURCE_ROOT" status --porcelain)" ]] || { echo "approved Apply source worktree is dirty" >&2; exit 16; }

for rel in \
  deploy/netcup/deploy_apply_staging_release.sh \
  deploy/netcup/verify_apply_staging_runtime_contract.sh \
  deploy/netcup/github_apply_staging_deploy_gateway.sh
do
  [[ -f "$SOURCE_ROOT/$rel" ]] || { echo "missing approved Apply deployment source: $rel" >&2; exit 17; }
  bash -n "$SOURCE_ROOT/$rel"
done

read -r key_type key_blob _ < "$PUBLIC_KEY_FILE"
[[ "$key_type" == "ssh-ed25519" ]] || { echo "Apply staging deployment key must be ssh-ed25519" >&2; exit 18; }
[[ "$key_blob" =~ ^[A-Za-z0-9+/=]+$ ]] || { echo "invalid Apply staging public-key payload" >&2; exit 19; }
ssh-keygen -l -f "$PUBLIC_KEY_FILE" >/dev/null 2>&1 || { echo "Apply staging public key failed ssh-keygen validation" >&2; exit 20; }

docker network inspect "$HUNTER_NETWORK" >/dev/null 2>&1 || {
  echo "required Hunter staging application network is missing: $HUNTER_NETWORK" >&2
  exit 21
}
runuser -u "$TARGET_USER" -- docker info >/dev/null 2>&1 || {
  echo "target user lacks the existing Docker authority required by the restricted deploy wrapper" >&2
  exit 22
}

home="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
group="$(id -gn "$TARGET_USER")"
[[ -n "$home" && -d "$home" ]] || { echo "cannot resolve target user home" >&2; exit 23; }

ssh_dir="$home/.ssh"
authorized="$ssh_dir/authorized_keys"
deploy_target="$BIN_ROOT/deploy-apply-staging-release"
verify_target="$BIN_ROOT/verify-apply-staging-runtime-contract"
gateway_target="$BIN_ROOT/github-apply-staging-deploy-gateway"

install -d -o root -g root -m 0755 "$BIN_ROOT"
install -d -o "$TARGET_USER" -g "$group" -m 0750 "$STAGING_ROOT"
install -d -o "$TARGET_USER" -g "$group" -m 0750 "$STAGING_REPO"
install -d -o "$TARGET_USER" -g "$group" -m 0700 \
  "$STAGING_ROOT/runtime" "$STAGING_ROOT/backups" "$STAGING_ROOT/receipts"
install -d -o "$TARGET_USER" -g "$group" -m 0700 "$ssh_dir"

if [[ ! -d "$STAGING_REPO/.git" ]]; then
  if find "$STAGING_REPO" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
    echo "Apply staging repo directory is non-empty but is not a Git worktree" >&2
    exit 24
  fi
  runuser -u "$TARGET_USER" -- git -C "$STAGING_REPO" init -q
else
  [[ -z "$(runuser -u "$TARGET_USER" -- git -C "$STAGING_REPO" status --porcelain)" ]] || {
    echo "existing Apply staging repository is dirty" >&2
    exit 25
  }
fi

if [[ ! -e "$STAGING_ENV" ]]; then
  cat > "$STAGING_ENV" <<'ENV'
# MUNSHI Apply staging defaults. Add staging-only secrets separately.
MUNSHI_APPLY_LIVE_HANDOFF_ENABLED=false
MUNSHI_APPLY_HOSTED_PREPARE_WORKER_ENABLED=false
MUNSHI_APPLY_RESUME_UPLOAD_ENABLED=false
MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED=false
MUNSHI_HUNTER_EXECUTION_BRIDGE_STAGING_HTTP_ENABLED=false
MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED=false
MUNSHI_APPLY_HOSTED_SUBMIT_WORKER_ENABLED=false
MUNSHI_FINAL_REVIEW_ENABLED=false
MUNSHI_FINAL_SUBMIT_ENABLED=false
MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED=false
ENV
  chown "$TARGET_USER:$group" "$STAGING_ENV"
  chmod 0600 "$STAGING_ENV"
else
  [[ -f "$STAGING_ENV" ]] || { echo "staging.env exists but is not a regular file" >&2; exit 26; }
  chmod 0600 "$STAGING_ENV"
fi

backup_dir="$(mktemp -d /tmp/munshi-apply-staging-transport-install.XXXXXX)"
new_authorized="$(mktemp /tmp/munshi-apply-authorized-keys.XXXXXX)"

deploy_had=0
verify_had=0
gateway_had=0
authorized_had=0
[[ -e "$deploy_target" ]] && { cp -a "$deploy_target" "$backup_dir/deploy-apply-staging-release"; deploy_had=1; }
[[ -e "$verify_target" ]] && { cp -a "$verify_target" "$backup_dir/verify-apply-staging-runtime-contract"; verify_had=1; }
[[ -e "$gateway_target" ]] && { cp -a "$gateway_target" "$backup_dir/github-apply-staging-deploy-gateway"; gateway_had=1; }
[[ -e "$authorized" ]] && { cp -a "$authorized" "$backup_dir/authorized_keys"; authorized_had=1; }

rollback_install() {
  rc=$?
  trap - ERR
  echo "=== ROLLBACK APPLY STAGING TRANSPORT INSTALL rc=$rc ===" >&2
  if (( deploy_had )); then cp -a "$backup_dir/deploy-apply-staging-release" "$deploy_target" || true; else rm -f "$deploy_target" || true; fi
  if (( verify_had )); then cp -a "$backup_dir/verify-apply-staging-runtime-contract" "$verify_target" || true; else rm -f "$verify_target" || true; fi
  if (( gateway_had )); then cp -a "$backup_dir/github-apply-staging-deploy-gateway" "$gateway_target" || true; else rm -f "$gateway_target" || true; fi
  if (( authorized_had )); then
    cp -a "$backup_dir/authorized_keys" "$authorized" || true
    chown "$TARGET_USER:$group" "$authorized" || true
    chmod 0600 "$authorized" || true
  else
    rm -f "$authorized" || true
  fi
  rm -f "$new_authorized" || true
  rm -rf "$backup_dir" || true
  echo "RESULT=APPLY_STAGING_TRANSPORT_INSTALL_ROLLED_BACK" >&2
  exit "$rc"
}
trap rollback_install ERR

install -o root -g root -m 0755 "$SOURCE_ROOT/deploy/netcup/deploy_apply_staging_release.sh" "$BIN_ROOT/.deploy-apply-staging-release.new"
install -o root -g root -m 0755 "$SOURCE_ROOT/deploy/netcup/verify_apply_staging_runtime_contract.sh" "$BIN_ROOT/.verify-apply-staging-runtime-contract.new"
install -o root -g root -m 0755 "$SOURCE_ROOT/deploy/netcup/github_apply_staging_deploy_gateway.sh" "$BIN_ROOT/.github-apply-staging-deploy-gateway.new"
mv -f "$BIN_ROOT/.deploy-apply-staging-release.new" "$deploy_target"
mv -f "$BIN_ROOT/.verify-apply-staging-runtime-contract.new" "$verify_target"
mv -f "$BIN_ROOT/.github-apply-staging-deploy-gateway.new" "$gateway_target"

if [[ -f "$authorized" ]]; then
  grep -v " $KEY_COMMENT$" "$authorized" > "$new_authorized" || true
fi
printf 'restrict,command="/opt/munshi/bin/github-apply-staging-deploy-gateway" %s %s %s\n' \
  "$key_type" "$key_blob" "$KEY_COMMENT" >> "$new_authorized"
install -o "$TARGET_USER" -g "$group" -m 0600 "$new_authorized" "$authorized"

bash -n "$deploy_target"
bash -n "$verify_target"
bash -n "$gateway_target"
if command -v sshd >/dev/null 2>&1; then
  sshd -t
fi

trap - ERR
rm -f "$new_authorized"
rm -rf "$backup_dir"

echo "APPROVED_SOURCE_SHA=$SOURCE_SHA"
echo "APPLY_STAGING_ROOT=$STAGING_ROOT"
echo "APPLY_STAGING_DEPLOY_WRAPPER=$deploy_target"
echo "APPLY_STAGING_VERIFIER=$verify_target"
echo "APPLY_STAGING_GATEWAY=$gateway_target"
echo "AUTHORIZED_KEYS=$authorized"
echo "HUNTER_DEPLOY_KEY_CHANGED=NO"
echo "PRIVATE_KEY_INSTALLED_ON_SERVER=NO"
echo "PRODUCTION_DEPLOYMENT_PERFORMED=NO"
echo "STAGING_DEPLOYMENT_PERFORMED=NO"
echo "INSTALL_TRANSACTION=PASS"
echo "RESULT=APPLY_STAGING_TRANSPORT_INSTALLED"

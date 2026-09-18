#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

APPLY_STAGING_DEPLOY="/opt/munshi/bin/deploy-apply-staging-release"
ORIGINAL="${SSH_ORIGINAL_COMMAND:-}"

if [[ "$ORIGINAL" =~ ^/opt/munshi/bin/deploy-apply-staging-release\ --target\ ([A-Za-z0-9][A-Za-z0-9._-]*)\ --commit\ ([0-9a-f]{40})\ --branch\ ([A-Za-z0-9._/-]+)$ ]]; then
  [[ -x "$APPLY_STAGING_DEPLOY" ]] || {
    echo "Apply staging deployment wrapper unavailable" >&2
    exit 70
  }
  target="${BASH_REMATCH[1]}"
  commit="${BASH_REMATCH[2]}"
  branch="${BASH_REMATCH[3]}"
  git check-ref-format --branch "$branch" >/dev/null || {
    echo "Apply staging deployment branch is invalid" >&2
    exit 72
  }
  exec "$APPLY_STAGING_DEPLOY" --target "$target" --commit "$commit" --branch "$branch"
fi

echo "request rejected by MUNSHI Apply staging deployment gateway" >&2
exit 71

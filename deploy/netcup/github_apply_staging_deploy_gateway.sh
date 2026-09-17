#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

APPLY_STAGING_DEPLOY="/opt/munshi/bin/deploy-apply-staging-release"
ORIGINAL="${SSH_ORIGINAL_COMMAND:-}"

if [[ "$ORIGINAL" =~ ^/opt/munshi/bin/deploy-apply-staging-release\ --commit\ ([0-9a-f]{40})\ --branch\ ([A-Za-z0-9._/-]+)$ ]]; then
  [[ -x "$APPLY_STAGING_DEPLOY" ]] || {
    echo "Apply staging deployment wrapper unavailable" >&2
    exit 70
  }
  commit="${BASH_REMATCH[1]}"
  branch="${BASH_REMATCH[2]}"
  git check-ref-format --branch "$branch" >/dev/null || {
    echo "Apply staging deployment branch is invalid" >&2
    exit 72
  }
  exec "$APPLY_STAGING_DEPLOY" --commit "$commit" --branch "$branch"
fi

echo "request rejected by MUNSHI Apply staging deployment gateway" >&2
exit 71

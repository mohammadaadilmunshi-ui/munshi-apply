#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_URL="https://github.com/Pickle-Pixel/ApplyPilot.git"
UPSTREAM_COMMIT="4a8d521f67f5139811c0a910ef37410f8e6d836a"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${SCRIPT_DIR}/upstream"

say() {
  printf '[applypilot-bootstrap] %s\n' "$*"
}

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

if [[ -d "${DEST}/.git" ]]; then
  say "Existing upstream checkout found. Refreshing refs."
  git -C "${DEST}" remote set-url origin "${UPSTREAM_URL}"
  git -C "${DEST}" fetch --quiet --no-tags origin "${UPSTREAM_COMMIT}"
elif [[ -e "${DEST}" ]]; then
  echo "Refusing to overwrite non-git path: ${DEST}" >&2
  exit 1
else
  say "Cloning isolated upstream checkout."
  git clone --quiet --filter=blob:none --no-checkout "${UPSTREAM_URL}" "${DEST}"
  git -C "${DEST}" fetch --quiet --no-tags origin "${UPSTREAM_COMMIT}"
fi

say "Checking out pinned revision ${UPSTREAM_COMMIT}."
git -C "${DEST}" checkout --quiet --detach "${UPSTREAM_COMMIT}"

ACTUAL_COMMIT="$(git -C "${DEST}" rev-parse HEAD)"
if [[ "${ACTUAL_COMMIT}" != "${UPSTREAM_COMMIT}" ]]; then
  echo "Pinned revision mismatch: expected ${UPSTREAM_COMMIT}, got ${ACTUAL_COMMIT}" >&2
  exit 1
fi

say "Upstream checkout ready at ${DEST}"
say "Revision: ${ACTUAL_COMMIT}"
say "This checkout is ignored by MUNSHI Git and remains governed by its upstream AGPL-3.0 license."
say "Do not add secrets, live credentials, or real application data to this directory."

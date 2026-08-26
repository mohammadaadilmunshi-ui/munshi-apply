#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

branch="${MUNSHI_UPDATE_BRANCH:-feat/v3-foundation-alignment}"
cd "${REPOSITORY_ROOT}"

if [[ -n "$(git status --porcelain)" ]]; then
  printf 'STOP: local changes detected; nothing was updated.\n' >&2
  git status --short >&2
  exit 1
fi
if [[ "$(git branch --show-current)" != "${branch}" ]]; then
  printf 'STOP: expected branch %s, found %s.\n' "${branch}" "$(git branch --show-current)" >&2
  exit 1
fi

printf 'Fetching %s...\n' "${branch}"
git fetch origin "${branch}"
git merge --ff-only "origin/${branch}"

printf 'Installing locked JavaScript dependencies and rebuilding extension...\n'
npm ci
npm run build
node scripts/verify-artifacts.mjs

runtime_root="$(resolve_runtime_root)"
native_python="${runtime_root}/native-host/bin/python"
native_launcher="${runtime_root}/native-host/bin/munshi-apply-native"
if [[ ! -x "${native_python}" || ! -x "${native_launcher}" ]]; then
  printf 'STOP: native runtime is not installed at %s. Run scripts/install.sh once.\n' "${runtime_root}" >&2
  exit 1
fi

printf 'Updating native companion in the existing private runtime...\n'
"${native_python}" -m pip install --upgrade --force-reinstall "${REPOSITORY_ROOT}/apps/native-host"
"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" migrate \
  --database "${runtime_root}/database/munshi-apply.sqlite" \
  --migrations "${REPOSITORY_ROOT}/migrations"
"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" native-smoke \
  --launcher "${native_launcher}" \
  --database "${runtime_root}/database/munshi-apply.sqlite" \
  --migrations "${REPOSITORY_ROOT}/migrations"

printf '\nMUNSHI Apply local runtime updated successfully.\nHEAD: %s\nExtension: %s\n' \
  "$(git rev-parse HEAD)" "${REPOSITORY_ROOT}/apps/extension/dist"

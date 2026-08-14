#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

no_fetch=false
extension_id=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-fetch) no_fetch=true; shift ;;
    --extension-id) extension_id="${2:-}"; shift 2 ;;
    --help)
      printf 'Usage: %s [--no-fetch] [--extension-id <id>]\n' "$0"
      exit 0
      ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

runtime_root="$(resolve_runtime_root)"
"${REPOSITORY_ROOT}/scripts/verify.sh" --skip-tests
backup_output="$("${REPOSITORY_ROOT}/scripts/backup.sh")"
printf '%s\n' "${backup_output}"

if [[ "${no_fetch}" == false ]]; then
  if [[ -n "$(git -C "${REPOSITORY_ROOT}" status --porcelain)" ]]; then
    printf 'Refusing update because the source worktree has uncommitted changes.\n' >&2
    exit 1
  fi
  git -C "${REPOSITORY_ROOT}" pull --ff-only
fi

npm ci --prefix "${REPOSITORY_ROOT}"
npm --offline run build --prefix "${REPOSITORY_ROOT}"
native_python="${runtime_root}/native-host/bin/python"
if [[ ! -x "${native_python}" ]]; then
  printf 'Installed native Python is unavailable: %s\n' "${native_python}" >&2
  exit 1
fi
"${native_python}" -m pip install --upgrade "${REPOSITORY_ROOT}/apps/native-host"
"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" migrate \
  --database "${runtime_root}/database/munshi-apply.sqlite" \
  --migrations "${REPOSITORY_ROOT}/migrations"

verify_args=()
if [[ -n "${extension_id}" ]]; then
  "${REPOSITORY_ROOT}/scripts/install-native-host.sh" --extension-id "${extension_id}"
  verify_args+=(--extension-id "${extension_id}")
fi
"${REPOSITORY_ROOT}/scripts/verify.sh" "${verify_args[@]}"
printf 'Update completed successfully.\n'

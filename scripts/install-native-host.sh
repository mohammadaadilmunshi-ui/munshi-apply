#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

extension_id=""
launcher="$(resolve_runtime_root)/native-host/bin/munshi-apply-native"
manifest_directory="$(default_manifest_directory)"
dry_run=false

usage() {
  printf 'Usage: %s --extension-id <32-character-id> [--launcher <path>] [--manifest-dir <path>] [--dry-run]\n' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --extension-id) extension_id="${2:-}"; shift 2 ;;
    --launcher) launcher="${2:-}"; shift 2 ;;
    --manifest-dir) manifest_directory="${2:-}"; shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    --help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ! "${extension_id}" =~ ^[a-p]{32}$ ]]; then
  printf 'A valid 32-character Edge extension ID (letters a-p) is required.\n' >&2
  exit 2
fi

manifest_path="${manifest_directory}/systems.munshi.apply.json"
if [[ "${dry_run}" == true ]]; then
  printf 'Would register native host %s for extension %s at %s\n' \
    "${launcher}" "${extension_id}" "${manifest_path}"
  exit 0
fi

if [[ ! -x "${launcher}" ]]; then
  printf 'Native launcher is not executable: %s\n' "${launcher}" >&2
  exit 1
fi

"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" native-manifest \
  --extension-id "${extension_id}" \
  --launcher "${launcher}" \
  --output "${manifest_path}"
chmod 600 "${manifest_path}"

"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" native-smoke \
  --launcher "${launcher}" \
  --database "$(resolve_runtime_root)/database/munshi-apply.sqlite" \
  --migrations "${REPOSITORY_ROOT}/migrations"
printf 'Native Messaging registration verified: %s\n' "${manifest_path}"

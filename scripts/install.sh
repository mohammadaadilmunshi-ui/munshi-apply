#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

extension_id=""
manifest_directory=""
dry_run=false
skip_dependencies=false

usage() {
  printf 'Usage: %s [--extension-id <id>] [--manifest-dir <path>] [--skip-dependencies] [--dry-run]\n' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --extension-id) extension_id="${2:-}"; shift 2 ;;
    --manifest-dir) manifest_directory="${2:-}"; shift 2 ;;
    --skip-dependencies) skip_dependencies=true; shift ;;
    --dry-run) dry_run=true; shift ;;
    --help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$(uname -s)" in
  Darwin) printf 'Installing for macOS.\n' ;;
  Linux) printf 'Running Linux-compatible installation path (CI/development).\n' ;;
  *) printf 'MUNSHI Apply installation currently supports macOS and Linux.\n' >&2; exit 1 ;;
esac

require_command node
require_command npm
require_command "${PYTHON_BIN}"
runtime_root="$(resolve_runtime_root)"
database_path="${MUNSHI_DATABASE_PATH:-${runtime_root}/database/munshi-apply.sqlite}"
native_launcher="${runtime_root}/native-host/bin/munshi-apply-native"

if [[ "${dry_run}" == true ]]; then
  printf 'Would install source from %s with private runtime at %s\n' \
    "${REPOSITORY_ROOT}" "${runtime_root}"
  if [[ -z "${extension_id}" ]]; then
    printf 'Native manifest would be deferred until an Edge extension ID is supplied.\n'
  fi
  exit 0
fi

ensure_runtime_layout "${runtime_root}"

if [[ "${skip_dependencies}" == false ]]; then
  npm ci --prefix "${REPOSITORY_ROOT}"
fi
npm --offline run build --prefix "${REPOSITORY_ROOT}"

if [[ "${skip_dependencies}" == false ]]; then
  "${PYTHON_BIN}" -m venv "${runtime_root}/native-host"
  "${native_launcher%/*}/python" -m pip install --upgrade pip
  "${native_launcher%/*}/python" -m pip install "${REPOSITORY_ROOT}/apps/native-host"
fi

"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" migrate \
  --database "${database_path}" \
  --migrations "${REPOSITORY_ROOT}/migrations"
"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" health \
  --database "${database_path}" \
  --migrations "${REPOSITORY_ROOT}/migrations"

if [[ -n "${extension_id}" ]]; then
  native_args=(--extension-id "${extension_id}" --launcher "${native_launcher}")
  if [[ -n "${manifest_directory}" ]]; then
    native_args+=(--manifest-dir "${manifest_directory}")
  fi
  "${REPOSITORY_ROOT}/scripts/install-native-host.sh" "${native_args[@]}"
else
  printf 'Native Messaging manifest deferred: rerun with --extension-id after loading the extension.\n'
fi

if [[ -n "${MUNSHI_N8N_WEBHOOK_URL:-}" && -z "${MUNSHI_N8N_WEBHOOK_SECRET:-}" ]]; then
  printf 'MUNSHI_N8N_WEBHOOK_SECRET is required when n8n is enabled.\n' >&2
  exit 1
fi

report_path="${runtime_root}/diagnostics/installation-report.json"
report_args=(
  installation-report
  --runtime-root "${runtime_root}"
  --output "${report_path}"
)
if [[ -n "${extension_id}" ]]; then
  report_args+=(--extension-id "${extension_id}")
fi
"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" "${report_args[@]}"
printf 'Installation complete. Report: %s\n' "${report_path}"

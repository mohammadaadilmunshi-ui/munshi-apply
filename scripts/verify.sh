#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

skip_tests=false
source_only=false
runtime_only=false
extension_id=""
manifest_directory=""

usage() {
  printf 'Usage: %s [--skip-tests] [--source-only] [--runtime-only] [--extension-id <id>] [--manifest-dir <path>]\n' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests) skip_tests=true; shift ;;
    --source-only) source_only=true; shift ;;
    --runtime-only) runtime_only=true; shift ;;
    --extension-id) extension_id="${2:-}"; shift 2 ;;
    --manifest-dir) manifest_directory="${2:-}"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "${source_only}" == true && "${runtime_only}" == true ]]; then
  printf '%s\n' '--source-only and --runtime-only cannot be combined.' >&2
  exit 2
fi

runtime_root="$(resolve_runtime_root)"
database_path="${MUNSHI_DATABASE_PATH:-${runtime_root}/database/munshi-apply.sqlite}"
manifest_path=""
if [[ -n "${extension_id}" ]]; then
  if [[ -z "${manifest_directory}" ]]; then
    manifest_directory="$(default_manifest_directory)"
  fi
  manifest_path="${manifest_directory}/systems.munshi.apply.json"
fi

# Source/development quality belongs to CI or an explicitly requested source
# verification. Installed production runtimes intentionally do not carry
# ruff/pytest and must not fail verification because developer tools are absent.
if [[ "${runtime_only}" == false && "${skip_tests}" == false ]]; then
  npm --offline run format:check --prefix "${REPOSITORY_ROOT}"
  npm --offline run lint --prefix "${REPOSITORY_ROOT}"
  npm --offline run typecheck --prefix "${REPOSITORY_ROOT}"
  npm --offline test --prefix "${REPOSITORY_ROOT}"
  npm --offline run build --prefix "${REPOSITORY_ROOT}"
  npm --offline run verify --prefix "${REPOSITORY_ROOT}"
  npm --offline run secret:scan --prefix "${REPOSITORY_ROOT}"
  "${PYTHON_BIN}" -m ruff check "${REPOSITORY_ROOT}/apps/native-host"
  "${PYTHON_BIN}" -m ruff format --check "${REPOSITORY_ROOT}/apps/native-host"
  "${PYTHON_BIN}" -m pytest "${REPOSITORY_ROOT}/apps/native-host"
fi

if [[ ! -f "${REPOSITORY_ROOT}/apps/extension/dist/manifest.json" ]]; then
  printf 'Extension build is missing. Run npm run build.\n' >&2
  exit 1
fi
node "${REPOSITORY_ROOT}/scripts/verify-artifacts.mjs"

"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" health \
  --database "${database_path}" \
  --migrations "${REPOSITORY_ROOT}/migrations"

if [[ -n "${MUNSHI_N8N_WEBHOOK_URL:-}" ]]; then
  if [[ -z "${MUNSHI_N8N_WEBHOOK_SECRET:-}" ]]; then
    printf 'n8n URL is configured without a webhook secret.\n' >&2
    exit 1
  fi
  "${PYTHON_BIN}" -c \
    'import sys, urllib.parse; value=urllib.parse.urlparse(sys.argv[1]); raise SystemExit(0 if value.scheme in {"http", "https"} and value.netloc else 1)' \
    "${MUNSHI_N8N_WEBHOOK_URL}"
fi

if [[ "${source_only}" == true ]]; then
  "${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" native-smoke \
    --python "${PYTHON_BIN}" \
    --module-root "${REPOSITORY_ROOT}/apps/native-host/src" \
    --database "${database_path}" \
    --migrations "${REPOSITORY_ROOT}/migrations"
else
  native_launcher="${runtime_root}/native-host/bin/munshi-apply-native"
  if [[ ! -x "${native_launcher}" ]]; then
    printf 'Installed native launcher is unavailable: %s\n' "${native_launcher}" >&2
    exit 1
  fi
  "${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" native-smoke \
    --launcher "${native_launcher}" \
    --database "${database_path}" \
    --migrations "${REPOSITORY_ROOT}/migrations"
fi

if [[ -n "${manifest_path}" ]]; then
  "${PYTHON_BIN}" -c \
    'import json, pathlib, sys; data=json.loads(pathlib.Path(sys.argv[1]).read_text()); expected=f"chrome-extension://{sys.argv[2]}/"; raise SystemExit(0 if data.get("name")=="systems.munshi.apply" and expected in data.get("allowed_origins", []) and pathlib.Path(data.get("path", "")).is_file() else 1)' \
    "${manifest_path}" "${extension_id}"
fi

printf 'MUNSHI Apply verification passed.\n'

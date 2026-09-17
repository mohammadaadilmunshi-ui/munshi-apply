#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

runtime_root="$(resolve_runtime_root)"
backup_path="$("${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" backup --runtime-root "${runtime_root}")"
"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" verify-backup --backup "${backup_path}"
printf 'Backup created and verified: %s\n' "${backup_path}"

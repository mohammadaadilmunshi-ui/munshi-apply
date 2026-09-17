#!/usr/bin/env bash

set -euo pipefail
repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

forbidden="$(
  git -C "${repository_root}" ls-files \
    '*.sqlite' '*.sqlite-*' '*.db' '*.env' '*.pem' '*.key' '*.p12' '*.pfx' \
    '*.pdf' '*.doc' '*.docx' \
    'runtime-data/**' 'private/**' 'secrets/**' 'backups/**' \
    'real-resumes/**' 'application-data/**' 'diagnostics-private/**' \
    'reports/generated/**' \
    | grep -v '^backups/\.gitkeep$' || true
)"

if [[ -n "${forbidden}" ]]; then
  printf 'Forbidden local, credential, or personal artifacts are tracked:\n%s\n' \
    "${forbidden}" >&2
  exit 1
fi

printf 'Repository private-data boundary passed.\n'

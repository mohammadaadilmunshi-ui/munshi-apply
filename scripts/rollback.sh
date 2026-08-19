#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

version="${1:-}"
shift || true
dry_run=false
extension_id=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) dry_run=true; shift ;;
    --extension-id) extension_id="${2:-}"; shift 2 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

if [[ -z "${version}" ]]; then
  printf 'Usage: %s <version-or-git-ref> [--extension-id <id>] [--dry-run]\n' "$0" >&2
  exit 2
fi
if ! git -C "${REPOSITORY_ROOT}" rev-parse --verify --quiet "${version}^{commit}" >/dev/null; then
  printf 'Rollback target is not a known commit or tag: %s\n' "${version}" >&2
  exit 1
fi

runtime_root="$(resolve_runtime_root)"
safe_version="${version//\//-}"
release_root="${runtime_root}/releases/${safe_version}"
if [[ "${dry_run}" == true ]]; then
  printf 'Would preserve the database, create a backup, and activate code release %s at %s\n' \
    "${version}" "${release_root}"
  exit 0
fi
if [[ -e "${release_root}" ]]; then
  printf 'Rollback release directory already exists: %s\n' "${release_root}" >&2
  exit 1
fi

"${REPOSITORY_ROOT}/scripts/backup.sh"
staging_directory="$(mktemp -d "${TMPDIR:-/tmp}/munshi-rollback.XXXXXX")"
trap 'rm -rf "${staging_directory}"' EXIT
git -C "${REPOSITORY_ROOT}" archive "${version}" | tar -x -C "${staging_directory}"

npm ci --prefix "${staging_directory}"
npm --offline run build --prefix "${staging_directory}"
"${PYTHON_BIN}" -m venv "${staging_directory}/native-host"
"${staging_directory}/native-host/bin/python" -m pip install \
  "${staging_directory}/apps/native-host"

mkdir -p "$(dirname "${release_root}")"
mv "${staging_directory}" "${release_root}"
trap - EXIT
ln -sfn "${release_root}" "${runtime_root}/current-release"

if [[ -n "${extension_id}" ]]; then
  "${release_root}/scripts/install-native-host.sh" \
    --extension-id "${extension_id}" \
    --launcher "${release_root}/native-host/bin/munshi-apply-native"
fi

"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" native-smoke \
  --launcher "${release_root}/native-host/bin/munshi-apply-native" \
  --database "${runtime_root}/database/munshi-apply.sqlite" \
  --migrations "${release_root}/migrations"
printf 'Rollback activated at %s. Application history was preserved.\n' "${release_root}"

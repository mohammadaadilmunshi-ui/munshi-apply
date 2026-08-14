#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIRECTORY}/../.." && pwd)"
PYTHON_BIN="${MUNSHI_PYTHON:-python3}"

resolve_runtime_root() {
  if [[ -n "${MUNSHI_RUNTIME_ROOT:-}" ]]; then
    printf '%s\n' "${MUNSHI_RUNTIME_ROOT}"
    return
  fi
  case "$(uname -s)" in
    Darwin) printf '%s\n' "${HOME}/Library/Application Support/MUNSHI Apply" ;;
    Linux) printf '%s\n' "${XDG_DATA_HOME:-${HOME}/.local/share}/MUNSHI Apply" ;;
    *) printf '%s\n' "${HOME}/.munshi-apply" ;;
  esac
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Required command is unavailable: %s\n' "$1" >&2
    return 1
  fi
}

ensure_runtime_layout() {
  local runtime_root="$1"
  mkdir -p \
    "${runtime_root}/database" \
    "${runtime_root}/resumes/master" \
    "${runtime_root}/resumes/tailored" \
    "${runtime_root}/resumes/submitted" \
    "${runtime_root}/evidence" \
    "${runtime_root}/embeddings" \
    "${runtime_root}/learning" \
    "${runtime_root}/exports" \
    "${runtime_root}/logs" \
    "${runtime_root}/diagnostics" \
    "${runtime_root}/backups" \
    "${runtime_root}/secrets" \
    "${runtime_root}/settings" \
    "${runtime_root}/releases"
  chmod 700 "${runtime_root}" "${runtime_root}/secrets"
}

default_manifest_directory() {
  case "$(uname -s)" in
    Darwin)
      printf '%s\n' "${HOME}/Library/Application Support/Microsoft Edge/NativeMessagingHosts"
      ;;
    Linux)
      printf '%s\n' "${HOME}/.config/microsoft-edge/NativeMessagingHosts"
      ;;
    *)
      printf 'Native Messaging installation is supported on macOS and Linux.\n' >&2
      return 1
      ;;
  esac
}

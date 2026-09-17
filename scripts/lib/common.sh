#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIRECTORY}/../.." && pwd)"

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

python_is_supported() {
  local candidate="$1"
  "${candidate}" -c \
    'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' \
    >/dev/null 2>&1
}

resolve_python_bin() {
  local candidate=""
  local resolved=""
  local runtime_python=""

  if [[ -n "${MUNSHI_PYTHON:-}" ]]; then
    if ! resolved="$(command -v "${MUNSHI_PYTHON}" 2>/dev/null)"; then
      printf 'Configured MUNSHI_PYTHON is unavailable: %s\n' "${MUNSHI_PYTHON}" >&2
      return 1
    fi
    if ! python_is_supported "${resolved}"; then
      printf 'MUNSHI Apply requires Python 3.12 or newer; configured interpreter is unsupported: %s\n' \
        "${resolved}" >&2
      return 1
    fi
    printf '%s\n' "${resolved}"
    return
  fi

  runtime_python="$(resolve_runtime_root)/native-host/bin/python"
  if [[ -x "${runtime_python}" ]] && python_is_supported "${runtime_python}"; then
    printf '%s\n' "${runtime_python}"
    return
  fi

  for candidate in python3 python3.13 python3.12; do
    if resolved="$(command -v "${candidate}" 2>/dev/null)" && python_is_supported "${resolved}"; then
      printf '%s\n' "${resolved}"
      return
    fi
  done

  printf 'MUNSHI Apply requires Python 3.12 or newer. Install Python 3.12+ or set MUNSHI_PYTHON to a supported interpreter.\n' >&2
  return 1
}

PYTHON_BIN="$(resolve_python_bin)"

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

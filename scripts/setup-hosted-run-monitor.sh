#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

usage() {
  printf 'Usage: %s --ssh-host <user@trusted-host> --ssh-identity <absolute-private-key-path>\n' "$0"
}

ssh_host=""
ssh_identity=""
while (($#)); do
  case "$1" in
    --ssh-host) ssh_host="$2"; shift 2 ;;
    --ssh-identity) ssh_identity="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

if [[ -z "$ssh_host" || -z "$ssh_identity" ]]; then
  usage >&2
  exit 2
fi
command -v python3 >/dev/null || {
  echo "python3 is required to create owner-only configuration." >&2
  exit 3
}

# Only a path is stored: no private-key bytes or credentials are copied.
python3 - "$ssh_host" "$ssh_identity" <<'PY'
import json
import os
import re
import sys
import tempfile
from pathlib import Path

host, identity = sys.argv[1:]
if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.@_-]{1,160}", host):
    raise SystemExit("Invalid SSH destination.")
key_file = Path(identity).expanduser()
if not key_file.is_absolute() or not key_file.is_file():
    raise SystemExit("Use an existing absolute SSH private-key path.")
root = Path.home() / ".config" / "munshi-apply"
root.mkdir(mode=0o700, parents=True, exist_ok=True)
root.chmod(0o700)
destination = root / "hosted-monitor.json"
if destination.is_symlink():
    raise SystemExit("Configuration symlinks are not permitted.")
if destination.exists():
    raise SystemExit("Configuration already exists; refusing to overwrite.")
payload = {
    "ssh_host": host,
    "ssh_identity_file": str(key_file),
    "apply_container": "munshi-apply-production-apply-1",
}
fd, temporary = tempfile.mkstemp(prefix=".hosted-monitor-", dir=root)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as writer:
        json.dump(payload, writer, indent=2, sort_keys=True)
        writer.write("\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
except BaseException:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
print(f"Owner-only read-only observer configuration prepared: {destination}")
print("This does not start, resume, approve or submit an application.")
PY

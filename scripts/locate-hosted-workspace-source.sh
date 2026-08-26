#!/usr/bin/env bash

# Read-only locator for the separately deployed MUNSHI Apply owner workspace.
# Uses a bounded Python walk instead of recursive grep so very large Downloads
# trees cannot make the diagnostic appear hung indefinitely.
set -u

HOME_DIR="${HOME:?HOME is required}"
PYTHON_BIN="${MUNSHI_LOCATOR_PYTHON:-/usr/bin/python3}"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  echo "STOP: Python 3 is required for the read-only source locator."
  exit 1
fi

printf '%s\n' \
  "============================================================" \
  " MUNSHI APPLY — HOSTED WORKSPACE SOURCE LOCATOR V3" \
  " READ ONLY — NO PROJECT OR RUNTIME STATE IS MODIFIED" \
  "============================================================"

"$PYTHON_BIN" - "$HOME_DIR" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

home = Path(sys.argv[1]).expanduser().resolve()
roots = [
    home / "PROJECTS",
    home / "Projects",
    home / "Downloads",
    home / "Documents",
    home / "Desktop",
]

terms = (
    "Welcome, Aadil",
    "Create one-time pairing code",
    "paired devices",
    "Encrypted owner workspace",
    "answers to review",
    "Cloud control plane ready",
    "munshi-apply-mobile.mohammadaadilmunshi.chatgpt.site",
)

source_suffixes = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".html",
    ".css",
    ".json",
    ".vue",
    ".svelte",
}

pruned_names = {
    "node_modules",
    ".git",
    "dist",
    "dist-mobile",
    ".next",
    "coverage",
    ".cache",
    ".npm",
    ".Trash",
    "Library",
    "Applications",
    "venv",
    ".venv",
    "__pycache__",
    "build",
    ".turbo",
}

candidate_needles = ("munshi", "workspace", "mobile", "apply")
max_depth = 7
max_file_bytes = 5 * 1024 * 1024
max_files_per_root = 50_000

matches: set[str] = set()
candidates: set[str] = set()


def depth_from(root: Path, current: Path) -> int:
    try:
        return len(current.relative_to(root).parts)
    except ValueError:
        return max_depth + 1


for root in roots:
    if not root.is_dir():
        continue

    print(f"\nSearching source text: {root}", flush=True)
    files_seen = 0
    files_scanned = 0
    directories_seen = 0
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)
        directories_seen += 1
        depth = depth_from(root, current)

        # Never descend past the bounded search depth.
        if depth >= max_depth:
            dirnames[:] = []
        else:
            dirnames[:] = [
                name
                for name in dirnames
                if name not in pruned_names and not name.startswith(".Trash")
            ]

        lowered = current.name.casefold()
        if any(needle in lowered for needle in candidate_needles):
            candidates.add(str(current))

        for filename in filenames:
            files_seen += 1
            if files_seen > max_files_per_root:
                truncated = True
                dirnames[:] = []
                break

            path = current / filename
            if path.suffix.casefold() not in source_suffixes:
                continue

            try:
                stat = path.stat()
            except OSError:
                continue

            if stat.st_size > max_file_bytes:
                continue

            files_scanned += 1
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if any(term in text for term in terms):
                matches.add(str(path))

        if truncated:
            break

    status = "TRUNCATED AT SAFETY LIMIT" if truncated else "COMPLETE"
    print(
        f"Finished: {root} | status={status} | "
        f"dirs={directories_seen} | files_seen={files_seen} | source_files_scanned={files_scanned}",
        flush=True,
    )

print("\n=== EXACT SOURCE-TEXT MATCHES ===")
if matches:
    for path in sorted(matches):
        print(f"MATCH | {path}")
else:
    print("NONE")

print("\n=== CANDIDATE PROJECT DIRECTORIES ===")
if candidates:
    for path in sorted(candidates):
        print(f"CANDIDATE | {path}")
else:
    print("NONE")

print("\n=== CANONICAL REPOSITORY CHECK ===")
repo = home / "PROJECTS" / "munshi-apply"
if (repo / ".git").is_dir():
    print(f"Repo: {repo}")
    owner_workspace = repo / "apps" / "owner-workspace"
    print(f"apps/owner-workspace: {'PRESENT' if owner_workspace.is_dir() else 'ABSENT'}")
else:
    print("Canonical repo not found at expected path.")

print("\n=== INTERPRETATION ===")
if matches:
    print("At least one local file contains a hosted-workspace identifier.")
    print("Do not edit it yet; return this output for source verification.")
else:
    print("No local source file matched the hosted-workspace identifiers within the bounded common-root scan.")
    print("If candidate directories are also empty or unrelated, treat the deployed frontend as remote-only until exported/reattached.")

print("\n============================================================")
print(" END — READ ONLY — NO PROJECT STATE MODIFIED")
print("============================================================")
PY

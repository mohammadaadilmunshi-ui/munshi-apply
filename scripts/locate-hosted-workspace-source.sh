#!/usr/bin/env bash

# Read-only locator for the separately deployed MUNSHI Apply owner workspace.
# This intentionally does NOT use `set -e`: grep returns exit status 1 when a
# root contains no matches, and that must not abort the remaining search.
set -u

HOME_DIR="${HOME:?HOME is required}"

ROOTS=(
  "$HOME_DIR/PROJECTS"
  "$HOME_DIR/Projects"
  "$HOME_DIR/Downloads"
  "$HOME_DIR/Documents"
  "$HOME_DIR/Desktop"
)

TERMS=(
  "Welcome, Aadil"
  "Create one-time pairing code"
  "paired devices"
  "Encrypted owner workspace"
  "answers to review"
  "Cloud control plane ready"
  "munshi-apply-mobile.mohammadaadilmunshi.chatgpt.site"
)

SOURCE_GLOBS=(
  "*.ts"
  "*.tsx"
  "*.js"
  "*.jsx"
  "*.mjs"
  "*.cjs"
  "*.html"
  "*.css"
  "*.json"
  "*.vue"
  "*.svelte"
)

printf '%s\n' \
  "============================================================" \
  " MUNSHI APPLY — HOSTED WORKSPACE SOURCE LOCATOR V2" \
  " READ ONLY — NO PROJECT OR RUNTIME STATE IS MODIFIED" \
  "============================================================"

matches_file="$(mktemp -t munshi-owner-workspace-matches.XXXXXX)"
candidates_file="$(mktemp -t munshi-owner-workspace-candidates.XXXXXX)"
trap 'rm -f "$matches_file" "$candidates_file"' EXIT

search_root() {
  local root="$1"
  [ -d "$root" ] || return 0

  echo
  echo "Searching source text: $root"

  local include_args=()
  local pattern_args=()
  local glob
  local term

  for glob in "${SOURCE_GLOBS[@]}"; do
    include_args+=("--include=$glob")
  done
  for term in "${TERMS[@]}"; do
    pattern_args+=("-e" "$term")
  done

  # No-match is expected and must not stop the next root.
  grep -RIl \
    --exclude-dir=node_modules \
    --exclude-dir=.git \
    --exclude-dir=dist \
    --exclude-dir=dist-mobile \
    --exclude-dir=.next \
    --exclude-dir=coverage \
    --exclude-dir=.cache \
    --exclude-dir=.npm \
    --exclude-dir=.Trash \
    "${include_args[@]}" \
    "${pattern_args[@]}" \
    "$root" 2>/dev/null >>"$matches_file" || true

  echo "Scanning candidate project directories: $root"
  find "$root" \
    -maxdepth 5 \
    \( -name node_modules -o -name .git -o -name dist -o -name .next -o -name coverage \) -prune -o \
    -type d \
    \( -iname '*munshi*' -o -iname '*workspace*' -o -iname '*mobile*' -o -iname '*apply*' \) \
    -print 2>/dev/null >>"$candidates_file" || true
}

for root in "${ROOTS[@]}"; do
  search_root "$root"
done

echo
echo "=== EXACT SOURCE-TEXT MATCHES ==="
if [ -s "$matches_file" ]; then
  sort -u "$matches_file" | sed 's/^/MATCH | /'
else
  echo "NONE"
fi

echo
echo "=== CANDIDATE PROJECT DIRECTORIES ==="
if [ -s "$candidates_file" ]; then
  sort -u "$candidates_file" | sed 's/^/CANDIDATE | /'
else
  echo "NONE"
fi

echo
echo "=== CANONICAL REPOSITORY CHECK ==="
if [ -d "$HOME_DIR/PROJECTS/munshi-apply/.git" ]; then
  echo "Repo: $HOME_DIR/PROJECTS/munshi-apply"
  (
    cd "$HOME_DIR/PROJECTS/munshi-apply" || exit 0
    echo "Branch: $(git branch --show-current 2>/dev/null || echo unknown)"
    echo "HEAD:   $(git rev-parse HEAD 2>/dev/null || echo unknown)"
    if [ -d apps/owner-workspace ]; then
      echo "apps/owner-workspace: PRESENT"
    else
      echo "apps/owner-workspace: ABSENT"
    fi
  )
else
  echo "Canonical repo not found at expected path."
fi

echo
echo "=== INTERPRETATION ==="
if [ -s "$matches_file" ]; then
  echo "At least one local file contains a hosted-workspace identifier."
  echo "Do not edit it yet; return this output for source verification."
else
  echo "No local source file matched the hosted-workspace identifiers in the common roots."
  echo "If candidate directories are also empty or unrelated, treat the deployed frontend as remote-only until exported/reattached."
fi

echo
echo "============================================================"
echo " END — READ ONLY — NO PROJECT STATE MODIFIED"
echo "============================================================"

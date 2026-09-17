#!/usr/bin/env bash
set -u

SITE_URL="${1:-https://munshi-apply-mobile.mohammadaadilmunshi.chatgpt.site}"
TMP_ROOT="${TMPDIR:-/tmp}/munshi-apply-hosted-inspect-$$"
HTML="$TMP_ROOT/index.html"
HEADERS="$TMP_ROOT/headers.txt"
ASSETS="$TMP_ROOT/assets.txt"
MATCHES="$TMP_ROOT/matches.txt"
MAPS="$TMP_ROOT/maps.txt"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

mkdir -p "$TMP_ROOT/files"
: > "$ASSETS"
: > "$MATCHES"
: > "$MAPS"

echo "============================================================"
echo " MUNSHI APPLY — LIVE HOSTED WORKSPACE ASSET INSPECTOR"
echo " READ ONLY — NO AUTH COOKIES — NO PROJECT/RUNTIME CHANGES"
echo "============================================================"
echo
echo "Target: $SITE_URL"
echo

if ! command -v curl >/dev/null 2>&1; then
  echo "STOP: curl is not available."
  exit 1
fi

HTTP_CODE="$(curl \
  --silent \
  --show-error \
  --location \
  --max-time 20 \
  --connect-timeout 8 \
  --output "$HTML" \
  --dump-header "$HEADERS" \
  --write-out '%{http_code}' \
  "$SITE_URL" 2>/dev/null || true)"

FINAL_URL="$(curl \
  --silent \
  --show-error \
  --location \
  --max-time 20 \
  --connect-timeout 8 \
  --output /dev/null \
  --write-out '%{url_effective}' \
  "$SITE_URL" 2>/dev/null || true)"

echo "HTTP status: ${HTTP_CODE:-unavailable}"
echo "Final URL:   ${FINAL_URL:-unavailable}"

if [ ! -s "$HTML" ]; then
  echo
  echo "No HTML body could be retrieved without authentication."
  echo "RESULT: BROWSER_SESSION_REQUIRED"
  exit 0
fi

echo "HTML bytes:  $(wc -c < "$HTML" | tr -d ' ')"

python3 - "$HTML" "$SITE_URL" "$ASSETS" <<'PY'
import html.parser
import pathlib
import sys
from urllib.parse import urljoin, urlparse

html_path = pathlib.Path(sys.argv[1])
base = sys.argv[2]
out_path = pathlib.Path(sys.argv[3])

class Collector(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("src"):
            self.urls.append(attrs["src"])
        elif tag == "link" and attrs.get("href"):
            rel = attrs.get("rel", "")
            if "stylesheet" in rel or attrs["href"].endswith((".js", ".css", ".map")):
                self.urls.append(attrs["href"])

collector = Collector()
collector.feed(html_path.read_text(errors="replace"))
base_host = urlparse(base).netloc
seen = set()
with out_path.open("w") as out:
    for raw in collector.urls:
        absolute = urljoin(base, raw)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc != base_host:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        out.write(absolute + "\n")
PY

ASSET_COUNT="$(wc -l < "$ASSETS" | tr -d ' ')"
echo "Same-origin assets discovered: $ASSET_COUNT"

INDEX=0
while IFS= read -r ASSET_URL; do
  [ -n "$ASSET_URL" ] || continue
  INDEX=$((INDEX + 1))
  EXT="${ASSET_URL%%\?*}"
  EXT="${EXT##*.}"
  case "$EXT" in
    js|css|map|json) ;;
    *) EXT="asset" ;;
  esac
  DEST="$TMP_ROOT/files/asset-${INDEX}.${EXT}"
  CODE="$(curl \
    --silent \
    --show-error \
    --location \
    --max-time 20 \
    --connect-timeout 8 \
    --output "$DEST" \
    --write-out '%{http_code}' \
    "$ASSET_URL" 2>/dev/null || true)"
  if [ "$CODE" != "200" ] || [ ! -s "$DEST" ]; then
    rm -f "$DEST"
    continue
  fi
  if grep -aEqi \
    'Welcome, Aadil|Create one-time pairing code|paired devices|Encrypted owner workspace|answers to review|sync conflicts|Review applications' \
    "$DEST" 2>/dev/null; then
    printf 'MATCH | %s\n' "$ASSET_URL" >> "$MATCHES"
  fi
  MAP_REF="$(grep -aoE 'sourceMappingURL=[^[:space:]*]+' "$DEST" 2>/dev/null | tail -1 | sed 's/^sourceMappingURL=//' || true)"
  if [ -n "$MAP_REF" ] && [[ "$MAP_REF" != data:* ]]; then
    python3 - "$ASSET_URL" "$MAP_REF" >> "$MAPS" <<'PY'
import sys
from urllib.parse import urljoin
print(urljoin(sys.argv[1], sys.argv[2]))
PY
  fi
done < "$ASSETS"

sort -u "$MATCHES" -o "$MATCHES"
sort -u "$MAPS" -o "$MAPS"

echo
echo "=== WORKSPACE STRING MATCHES ==="
if [ -s "$MATCHES" ]; then
  cat "$MATCHES"
else
  echo "NONE"
fi

echo
echo "=== SOURCE MAP REFERENCES ==="
if [ -s "$MAPS" ]; then
  cat "$MAPS" | sed 's/^/MAP | /'
else
  echo "NONE"
fi

echo
echo "=== HTML MARKER CHECK ==="
if grep -aEqi \
  'Welcome, Aadil|Create one-time pairing code|paired devices|Encrypted owner workspace|answers to review|sync conflicts|Review applications' \
  "$HTML" 2>/dev/null; then
  echo "MATCH"
else
  echo "NONE"
fi

echo
echo "=== INTERPRETATION ==="
if [ -s "$MATCHES" ] || [ -s "$MAPS" ]; then
  echo "RESULT: DEPLOYED_ASSETS_RECOVERABLE"
  echo "The deployed site exposes build artifacts that can be used to identify/reconstruct the hosted frontend."
else
  echo "RESULT: NO_RECOVERABLE_PUBLIC_SOURCE"
  echo "No target UI strings or source-map references were found in unauthenticated public assets."
  echo "A signed-in browser-session inspection would be required next."
fi

echo
echo "============================================================"
echo " END — TEMPORARY DOWNLOADS REMOVED — NOTHING MODIFIED"
echo "============================================================"

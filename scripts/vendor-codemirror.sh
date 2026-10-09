#!/usr/bin/env bash
# Rebuild the vendored CodeMirror bundle for narrate studio (design D7).
# Every package version is pinned by scripts/codemirror/package-lock.json, so the
# bundle only changes when the pins do. Needs Node (for example `mise exec node@24 --`).
#   scripts/vendor-codemirror.sh            rebuild from the lock file
#   scripts/vendor-codemirror.sh --update   re-resolve package.json into a new lock file first
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
src=$root/scripts/codemirror
out=$root/src/narrate/studio/static/vendor/codemirror.js
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "$src/package.json" "$src/entry.js" "$work/"
if [[ "${1:-}" == "--update" ]]; then
  (cd "$work" && npm install --no-audit --no-fund --silent)
  cp "$work/package-lock.json" "$src/package-lock.json"
else
  cp "$src/package-lock.json" "$work/"
  (cd "$work" && npm ci --no-audit --no-fund --silent)
fi
(cd "$work" && ./node_modules/.bin/esbuild entry.js --bundle --format=esm --minify --legal-comments=eof \
  --target=es2022 --outfile="$out" --log-level=warning)
echo "$out: $(wc -c < "$out") bytes, sha256 $(sha256sum "$out" | cut -d' ' -f1)"

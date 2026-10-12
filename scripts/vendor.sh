#!/usr/bin/env bash
# Rebuild a vendored front-end bundle for narrate studio (design D7). Each bundle has a folder
# here with its entry.js, package.json and the package-lock.json that pins every version, so a
# bundle only changes when its pins do. Needs Node (for example `mise exec node@24 --`).
#   scripts/vendor.sh codemirror|fake-timers            rebuild from the lock file
#   scripts/vendor.sh codemirror|fake-timers --update   re-resolve package.json into a new lock file first
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
name=${1:-}
case "$name" in
  codemirror) format=(--format=esm) ;;  # imported by the studio's modules
  # Runs before a page's own scripts; Node's util is only reached when `process` exists
  fake-timers) format=(--format=iife --global-name=NarrateFakeTimers --external:util) ;;
  *) echo "usage: $0 codemirror|fake-timers [--update]" >&2; exit 2 ;;
esac
src=$root/scripts/$name
out=$root/src/narrate/studio/static/vendor/$name.js
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "$src/package.json" "$src/entry.js" "$work/"
if [[ "${2:-}" == "--update" ]]; then
  (cd "$work" && npm install --no-audit --no-fund --silent)
  cp "$work/package-lock.json" "$src/package-lock.json"
else
  cp "$src/package-lock.json" "$work/"
  (cd "$work" && npm ci --no-audit --no-fund --silent)
fi
(cd "$work" && ./node_modules/.bin/esbuild entry.js --bundle "${format[@]}" --platform=browser --minify \
  --legal-comments=eof --target=es2022 --outfile="$out" --log-level=warning)
echo "$out: $(wc -c < "$out") bytes, sha256 $(sha256sum "$out" | cut -d' ' -f1)"

#!/usr/bin/env bash
# Raycast only loads an extension `ray develop` announced once (raycast://cli/...); a plain
# `ray build -o` into an unknown folder is ignored. It stays registered after develop stops.
set -euo pipefail
ray=./node_modules/.bin/ray
open -g -a Raycast
log=$(mktemp)
"$ray" develop -I >"$log" 2>&1 &
pid=$!
stop() { kill -INT "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; rm -f "$log"; }
trap stop EXIT
for _ in $(seq 180); do
  grep -q 'built extension successfully' "$log" && break
  if ! kill -0 "$pid" 2>/dev/null; then cat "$log" >&2; exit 1; fi
  sleep 1
done
grep -q 'built extension successfully' "$log" || { cat "$log" >&2; echo 'ray develop: no build in 180 s' >&2; exit 1; }
stop
trap - EXIT
"$ray" build -e dist -o ~/.config/raycast/extensions/homebase-raycast

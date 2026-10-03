#!/usr/bin/env bash
# Build one extension package per platform into dist/ and validate each.
set -euo pipefail
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$ROOT/tools/fetch_wheels.py"
rm -rf "$ROOT/dist" && mkdir -p "$ROOT/dist"
"$BLENDER" --factory-startup --command extension build \
  --source-dir "$ROOT/ghosttown" --output-dir "$ROOT/dist" --split-platforms
for zip in "$ROOT"/dist/*.zip; do
  "$BLENDER" --factory-startup --command extension validate "$zip"
done
ls -la "$ROOT/dist"

#!/usr/bin/env bash
# Install the macOS arm64 package into a throwaway Blender profile and run one live build.
#   tools/smoke_installed.sh ["<address or lat, lon>"] [radius_m] [lidar]   (default: 320 Bay St, 150 m)
set -euo pipefail
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZIP="$(ls "$ROOT"/dist/ghosttown-*macos*arm64*.zip | head -1)"
export BLENDER_USER_RESOURCES="$(mktemp -d)"
"$BLENDER" --command extension install-file -r user_default -e "$ZIP"
"$BLENDER" --background --online-mode --python-exit-code 1 --python "$ROOT/tools/smoke_live.py" -- \
  "${1:-320 Bay St}" "${2:-150}" ${3:+"$3"}

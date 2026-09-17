#!/usr/bin/env bash
# Convert catalog phase-2/3 clips to .vrma.
# Prefers Motifect BVH from scripts/fetch_motion_packs.sh.
# Mixamo FBX named after catalog keys in data/mixamo/ still override when present.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/data/mixamo"
DEST="$ROOT/frontend/public/gestures"
FORCE=()
if [[ "${1:-}" == "--force" ]]; then
  FORCE=(--force)
elif [[ "${1:-}" != "" ]]; then
  SRC="$1"
fi

if [[ ! -d "$ROOT/data/mixamo/unpacked/daily/BVH" ]]; then
  echo "no Motifect packs yet; run: bash scripts/fetch_motion_packs.sh" >&2
fi

python3 "$ROOT/scripts/convert_gestures.py" "${FORCE[@]}"

shopt -s nullglob
fbx_files=("$SRC"/*.fbx "$SRC"/*.FBX)
if [[ ${#fbx_files[@]} -gt 0 ]]; then
  echo "also converting Mixamo FBX in $SRC"
  npx --yes fbx2vrma-converter@2.1.0 -i "$SRC" -o "$DEST"
fi

python3 "$ROOT/scripts/sync_gesture_catalog.py"
echo "gestures in $DEST"

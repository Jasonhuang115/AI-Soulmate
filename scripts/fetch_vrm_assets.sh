#!/usr/bin/env bash
# Sample VRM + phase-1 VRMA. Large binaries stay off git.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VRM_DIR="$ROOT/frontend/public/models/vrm"
GESTURE_DIR="$ROOT/frontend/public/gestures"
mkdir -p "$VRM_DIR" "$GESTURE_DIR"

download() {
  local url="$1"
  local dest="$2"
  if [[ -f "$dest" && -s "$dest" ]]; then
    echo "already have $dest"
    return 0
  fi
  echo "fetch $url"
  if curl -fL --retry 3 -A "Mozilla/5.0 ASM-fetch" -o "$dest" "$url"; then
    return 0
  fi
  rm -f "$dest"
  return 1
}

rm -f "$VRM_DIR/default.vrm"
if ! download "https://cdn.jsdelivr.net/gh/pixiv/ChatVRM@main/public/AvatarSample_B.vrm" \
  "$VRM_DIR/default.vrm"; then
  echo "ChatVRM sample blocked; trying three-vrm example model"
  download "https://cdn.jsdelivr.net/gh/pixiv/three-vrm@dev/packages/three-vrm/examples/models/VRM1_Constraint_Twist_Sample.vrm" \
    "$VRM_DIR/default.vrm"
fi
download "https://cdn.jsdelivr.net/gh/pixiv/ChatVRM@main/public/idle_loop.vrma" \
  "$GESTURE_DIR/idle_loop.vrma"

BASE="https://cdn.jsdelivr.net/gh/tk256ailab/vrm-viewer@main/VRMA"
for name in Angry Blush Clapping Goodbye Jump LookAround Relax Sad Sleepy Surprised Thinking; do
  download "$BASE/${name}.vrma" "$GESTURE_DIR/${name}.vrma"
done

echo "phase-1 assets in $VRM_DIR and $GESTURE_DIR"
echo "phase 2/3: bash scripts/fetch_motion_packs.sh && bash scripts/convert_mixamo_to_vrma.sh"

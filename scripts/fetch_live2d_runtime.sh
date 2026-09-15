#!/usr/bin/env bash
# Cubism 2 runtime for official sample models. Not Cubism Core (that one stays off-git).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/frontend/public/live2d.min.js"
if [[ -f "$DEST" ]]; then
  echo "already have $DEST"
  exit 0
fi
curl -L -o "$DEST" \
  "https://cdn.jsdelivr.net/gh/dylanNew/live2d/webgl/Live2D/lib/live2d.min.js"
echo "wrote $DEST"

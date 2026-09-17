#!/usr/bin/env bash
# Download Motifect humanoid packs (FBX+BVH) for phase 2/3 conversion.
# Not Mixamo. Binaries stay off git.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACK="$ROOT/data/mixamo/packs"
UNPACK="$ROOT/data/mixamo/unpacked"
mkdir -p "$PACK" "$UNPACK/daily" "$UNPACK/emotes" "$UNPACK/loco"

itch_download() {
  local page="$1"
  local fid="$2"
  local dest="$3"
  if [[ -f "$dest" && -s "$dest" ]]; then
    echo "already have $dest"
    return 0
  fi
  echo "fetch $page file $fid"
  local url
  url="$(curl -sL -A "Mozilla/5.0 ASM-fetch" -H "Referer: $page" -X POST "$page/file/$fid" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['url'])")"
  curl -fL --retry 3 -A "Mozilla/5.0 ASM-fetch" -o "$dest" "$url"
}

itch_download "https://motifect.itch.io/motifect-daily-life-motion-pack" 17697512 "$PACK/motifect-daily-life.zip"
itch_download "https://motifect.itch.io/motifect-emotes-social-motion-pack" 17697540 "$PACK/motifect-emotes.zip"
itch_download "https://motifect.itch.io/motifect-locomotion-motion-pack" 17883914 "$PACK/motifect-locomotion.zip"

unzip -qo "$PACK/motifect-daily-life.zip" -d "$UNPACK/daily"
unzip -qo "$PACK/motifect-emotes.zip" -d "$UNPACK/emotes"
unzip -qo "$PACK/motifect-locomotion.zip" -d "$UNPACK/loco"

echo "unpacked BVH into $UNPACK"
echo "next: python3 scripts/convert_gestures.py"

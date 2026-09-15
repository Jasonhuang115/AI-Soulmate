#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/data/models"
mkdir -p "$DEST"
cd "$DEST"

if [[ ! -f silero_vad.onnx ]]; then
  curl -L -o silero_vad.onnx \
    https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx
fi

ASR=sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20
if [[ ! -d "$ASR" ]]; then
  curl -L -o "$ASR.tar.bz2" \
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${ASR}.tar.bz2"
  tar xf "$ASR.tar.bz2"
  rm -f "$ASR.tar.bz2"
fi

echo "models in $DEST"

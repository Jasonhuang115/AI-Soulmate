from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def model_dir() -> Path:
    return repo_root() / "data" / "models"


def vad_path() -> Path:
    return model_dir() / "silero_vad.onnx"


def asr_dir() -> Path:
    return model_dir() / "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"


def hotwords_path() -> Path:
    return repo_root() / "data" / "hotwords.txt"

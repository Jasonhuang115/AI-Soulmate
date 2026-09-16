from __future__ import annotations

import logging
from pathlib import Path

from asm.perception.paths import asr_dir, hotwords_path

logger = logging.getLogger(__name__)


class SherpaAsr:
    def __init__(self, root: Path | None = None) -> None:
        import sherpa_onnx

        folder = root or asr_dir()
        encoder = folder / "encoder-epoch-99-avg-1.int8.onnx"
        decoder = folder / "decoder-epoch-99-avg-1.onnx"
        joiner = folder / "joiner-epoch-99-avg-1.int8.onnx"
        tokens = folder / "tokens.txt"
        for path in (encoder, decoder, joiner, tokens):
            if not path.exists():
                raise FileNotFoundError(path)
        kwargs = dict(
            tokens=str(tokens),
            encoder=str(encoder),
            decoder=str(decoder),
            joiner=str(joiner),
            num_threads=1,
            sample_rate=16000,
            feature_dim=80,
            decoding_method="greedy_search",
            provider="cpu",
        )
        hot = hotwords_path()
        if hot.exists() and hot.read_text(encoding="utf-8").strip():
            kwargs["decoding_method"] = "modified_beam_search"
            kwargs["hotwords_file"] = str(hot)
            kwargs["max_active_paths"] = 4
        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(**kwargs)
        self._stream = self._recognizer.create_stream()
        self._last = ""

    def feed(self, samples: list[float], sample_rate: int = 16000) -> str | None:
        self._stream.accept_waveform(sample_rate, samples)
        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)
        text = self._recognizer.get_result(self._stream).strip()
        if text and text != self._last:
            self._last = text
            return text
        return None

    def reset(self) -> None:
        self._stream = self._recognizer.create_stream()
        self._last = ""

    def finalize(self) -> str:
        self._stream.input_finished()
        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)
        text = self._recognizer.get_result(self._stream).strip() or self._last
        self.reset()
        return text


def load_asr() -> SherpaAsr | None:
    try:
        return SherpaAsr()
    except (FileNotFoundError, ImportError, ValueError) as exc:
        logger.warning("asr unavailable: %s", exc)
        return None

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from asm.perception.paths import vad_path

logger = logging.getLogger(__name__)


class SileroVad:
    def __init__(self, model: Path | None = None, sample_rate: int = 16000) -> None:
        import sherpa_onnx

        path = model or vad_path()
        if not path.exists():
            raise FileNotFoundError(path)
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(path)
        # Keep one streaming ASR window across syllable gaps. Orchestrator
        # still owns 300/700 ms after a *real* pause.
        config.silero_vad.min_silence_duration = 0.4
        config.silero_vad.min_speech_duration = 0.15
        config.silero_vad.threshold = 0.5
        config.sample_rate = sample_rate
        self._vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=20)
        self._speaking = False
        self._window = config.silero_vad.window_size
        self._pending: list[float] = []

    def feed(self, samples: list[float]) -> list[str]:
        events: list[str] = []
        self._pending.extend(samples)
        window = self._window
        while len(self._pending) >= window:
            chunk = self._pending[:window]
            del self._pending[:window]
            self._vad.accept_waveform(chunk)
            events.extend(self._edges())
        return events

    def flush(self) -> list[str]:
        events: list[str] = []
        window = self._window
        if self._pending:
            chunk = list(self._pending)
            self._pending.clear()
            if len(chunk) < window:
                chunk.extend([0.0] * (window - len(chunk)))
            self._vad.accept_waveform(chunk)
            events.extend(self._edges())
        self._vad.flush()
        events.extend(self._edges())
        if self._speaking:
            self._speaking = False
            events.append("end")
        while not self._vad.empty():
            self._vad.pop()
        return events

    def _edges(self) -> list[str]:
        events: list[str] = []
        speaking = self._vad.is_speech_detected()
        if speaking and not self._speaking:
            self._speaking = True
            events.append("start")
        elif not speaking and self._speaking:
            self._speaking = False
            events.append("end")
        while not self._vad.empty():
            self._vad.pop()
        return events


def load_vad(on_missing: Callable[[], None] | None = None) -> SileroVad | None:
    try:
        return SileroVad()
    except (FileNotFoundError, ImportError, ValueError, RuntimeError) as exc:
        logger.warning("vad unavailable: %s", exc)
        if on_missing:
            on_missing()
        return None

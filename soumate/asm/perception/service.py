from __future__ import annotations

import math
import struct

from asm.core.bus import EventBus
from asm.core.events import (
    DialogState,
    Duck,
    MicState,
    PartialTranscript,
    SpeechEnded,
    SpeechStarted,
    StateChanged,
    Unduck,
    UtteranceEnd,
)
from asm.perception.asr_sherpa import SherpaAsr, load_asr
from asm.perception.pcm import PcmFramer
from asm.perception.vad_silero import SileroVad, load_vad

_SILENCE_RMS = 0.012
_SILENCE_SAMPLES = 19200  # 1.2 s at 16 kHz; syllable gaps must not end a turn


def _pcm_to_float(pcm16: bytes) -> list[float]:
    count = len(pcm16) // 2
    samples = struct.unpack("<" + "h" * count, pcm16[: count * 2])
    return [s / 32768.0 for s in samples]


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


class SpeechPerceiver:
    def __init__(
        self,
        bus: EventBus,
        vad: SileroVad | None = None,
        asr: SherpaAsr | None = None,
    ) -> None:
        self._bus = bus
        self._vad = vad
        self._asr = asr
        self._framer = PcmFramer()
        self._asr_live = True
        self._ducking = False
        self._in_utterance = False
        self._silence_samples = 0
        bus.subscribe(StateChanged, self._on_state)
        bus.subscribe(Duck, self._on_duck)
        bus.subscribe(Unduck, self._on_unduck)
        bus.subscribe(MicState, self._on_mic)

    @property
    def listening(self) -> bool:
        return self._vad is not None and self._asr is not None

    @classmethod
    def maybe(cls, bus: EventBus) -> SpeechPerceiver:
        return cls(bus, load_vad(), load_asr())

    async def feed(self, pcm16: bytes) -> None:
        for frame in self._framer.push(pcm16):
            await self._feed_frame(frame)

    async def _feed_frame(self, pcm16: bytes) -> None:
        samples = _pcm_to_float(pcm16)
        edges: list[str] = []
        if self._vad is not None:
            edges = self._vad.feed(samples)
        for edge in edges:
            if edge == "start":
                self._in_utterance = True
                self._silence_samples = 0
                await self._bus.publish(SpeechStarted())
        if self._asr_live and self._asr is not None:
            text = self._asr.feed(samples)
            if text:
                if not self._in_utterance:
                    self._in_utterance = True
                    await self._bus.publish(SpeechStarted())
                await self._bus.publish(PartialTranscript(text))
        if self._in_utterance and self._asr_live:
            vad_busy = bool(getattr(self._vad, "_speaking", False))
            if not vad_busy:
                if _rms(samples) < _SILENCE_RMS:
                    self._silence_samples += len(samples)
                else:
                    self._silence_samples = 0
                if self._silence_samples >= _SILENCE_SAMPLES:
                    await self._emit_end()
        for edge in edges:
            if edge == "end":
                await self._emit_end()

    async def _apply_edges(self, edges: list[str]) -> None:
        for edge in edges:
            if edge == "start":
                self._in_utterance = True
                self._silence_samples = 0
                await self._bus.publish(SpeechStarted())
            elif edge == "end":
                await self._emit_end()

    async def _emit_end(self) -> None:
        if not self._in_utterance:
            return
        self._in_utterance = False
        self._silence_samples = 0
        await self._bus.publish(SpeechEnded())
        final = self._asr.finalize() if self._asr is not None else ""
        if final:
            await self._bus.publish(UtteranceEnd(final))

    async def flush(self) -> None:
        edges: list[str] = []
        flush = getattr(self._vad, "flush", None)
        if flush is not None:
            edges = flush() or []
        await self._apply_edges(edges)
        await self._emit_end()

    def _pause_asr(self) -> None:
        self._asr_live = False
        self._in_utterance = False
        self._silence_samples = 0
        reset = getattr(self._asr, "reset", None)
        if reset is not None:
            reset()

    def _resume_asr(self, *, reset: bool) -> None:
        if reset:
            reset_fn = getattr(self._asr, "reset", None)
            if reset_fn is not None:
                reset_fn()
        self._asr_live = True

    async def _on_state(self, event: StateChanged) -> None:
        if event.state == DialogState.SPEAKING:
            if not self._ducking:
                self._pause_asr()
            return
        if not self._asr_live:
            self._resume_asr(reset=True)

    async def _on_duck(self, event: Duck) -> None:
        del event
        self._ducking = True
        self._resume_asr(reset=True)

    async def _on_unduck(self, event: Unduck) -> None:
        del event
        self._ducking = False
        self._pause_asr()

    async def _on_mic(self, event: MicState) -> None:
        if not event.open:
            await self.flush()

    async def close(self) -> None:
        self._ducking = False
        self._resume_asr(reset=True)

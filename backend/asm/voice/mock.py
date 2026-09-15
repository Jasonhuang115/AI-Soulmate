from __future__ import annotations

import math
import struct
from collections.abc import AsyncIterator

from asm.core.events import AudioChunk
from asm.voice.mouth_energy import mouth_energy


class MockTTS:
    def __init__(self, sample_rate: int = 24000, duration_s: float = 0.2) -> None:
        self.sample_rate = sample_rate
        self.duration_s = duration_s
        self._cancelled: set[str] = set()

    async def synthesize(
        self, turn_id: str, sentence_idx: int, text: str
    ) -> AsyncIterator[AudioChunk]:
        del text
        if turn_id in self._cancelled:
            return
        n = int(self.sample_rate * self.duration_s)
        pcm = bytearray()
        for i in range(n):
            sample = int(16000 * math.sin(2 * math.pi * 220 * i / self.sample_rate))
            pcm.extend(struct.pack("<h", sample))
        raw = bytes(pcm)
        energy = tuple(mouth_energy(raw, self.sample_rate))
        if turn_id in self._cancelled:
            return
        yield AudioChunk(
            turn_id=turn_id,
            sentence_idx=sentence_idx,
            seq=0,
            pcm16=raw,
            sample_rate=self.sample_rate,
            mouth_energy=energy,
        )

    async def cancel(self, turn_id: str) -> None:
        self._cancelled.add(turn_id)

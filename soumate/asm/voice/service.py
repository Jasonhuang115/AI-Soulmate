from __future__ import annotations

import asyncio
import logging

from asm.core.bus import EventBus
from asm.core.events import AudioChunk, Cancel, SentenceEnd
from asm.core.interfaces import TTSEngine

logger = logging.getLogger(__name__)


class VoiceService:
    def __init__(self, bus: EventBus, engine: TTSEngine) -> None:
        self._bus = bus
        self._engine = engine
        self._cancelled: set[str] = set()
        self._next_idx: dict[str, int] = {}
        self._held: dict[str, dict[int, list[AudioChunk]]] = {}
        self._tasks: dict[str, set[asyncio.Task[None]]] = {}
        bus.subscribe(SentenceEnd, self._on_sentence)
        bus.subscribe(Cancel, self._on_cancel)

    async def _on_cancel(self, event: Cancel) -> None:
        self._cancelled.add(event.turn_id)
        await self._engine.cancel(event.turn_id)
        self._held.pop(event.turn_id, None)
        for task in list(self._tasks.get(event.turn_id, set())):
            task.cancel()

    async def _on_sentence(self, event: SentenceEnd) -> None:
        if event.turn_id in self._cancelled:
            return
        self._next_idx.setdefault(event.turn_id, 0)
        self._held.setdefault(event.turn_id, {})
        task = asyncio.create_task(self._synth(event))
        self._tasks.setdefault(event.turn_id, set()).add(task)
        task.add_done_callback(lambda done: self._tasks.get(event.turn_id, set()).discard(done))

    async def _synth(self, event: SentenceEnd) -> None:
        chunks: list[AudioChunk] = []
        try:
            async for chunk in self._engine.synthesize(event.turn_id, event.sentence_idx, event.text):
                if event.turn_id in self._cancelled:
                    return
                chunks.append(chunk)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("tts failed turn=%s idx=%s", event.turn_id, event.sentence_idx)
            return
        if event.turn_id in self._cancelled:
            return
        self._held[event.turn_id][event.sentence_idx] = chunks
        await self._flush(event.turn_id)

    async def _flush(self, turn_id: str) -> None:
        held = self._held.get(turn_id, {})
        while self._next_idx.get(turn_id, 0) in held:
            idx = self._next_idx[turn_id]
            for chunk in held.pop(idx):
                if turn_id in self._cancelled:
                    return
                await self._bus.publish(chunk)
            self._next_idx[turn_id] = idx + 1

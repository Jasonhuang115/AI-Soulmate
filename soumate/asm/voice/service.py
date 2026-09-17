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
        self._buf: dict[str, dict[int, list[AudioChunk]]] = {}
        self._done: dict[str, set[int]] = {}
        self._tasks: dict[str, set[asyncio.Task[None]]] = {}
        self._lock = asyncio.Lock()
        bus.subscribe(SentenceEnd, self._on_sentence)
        bus.subscribe(Cancel, self._on_cancel)

    async def _on_cancel(self, event: Cancel) -> None:
        self._cancelled.add(event.turn_id)
        await self._engine.cancel(event.turn_id)
        async with self._lock:
            self._buf.pop(event.turn_id, None)
            self._done.pop(event.turn_id, None)
            self._next_idx.pop(event.turn_id, None)
        for task in list(self._tasks.get(event.turn_id, set())):
            task.cancel()

    async def _on_sentence(self, event: SentenceEnd) -> None:
        if event.turn_id in self._cancelled:
            return
        self._next_idx.setdefault(event.turn_id, 0)
        self._buf.setdefault(event.turn_id, {})
        self._done.setdefault(event.turn_id, set())
        task = asyncio.create_task(self._synth(event))
        self._tasks.setdefault(event.turn_id, set()).add(task)
        task.add_done_callback(lambda done: self._tasks.get(event.turn_id, set()).discard(done))

    async def _synth(self, event: SentenceEnd) -> None:
        try:
            async for chunk in self._engine.synthesize(event.turn_id, event.sentence_idx, event.text):
                if event.turn_id in self._cancelled:
                    return
                async with self._lock:
                    if event.turn_id in self._cancelled:
                        return
                    await self._emit_chunk(event.turn_id, event.sentence_idx, chunk)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("tts failed turn=%s idx=%s", event.turn_id, event.sentence_idx)
            return
        if event.turn_id in self._cancelled:
            return
        async with self._lock:
            if event.turn_id in self._cancelled:
                return
            self._done.setdefault(event.turn_id, set()).add(event.sentence_idx)
            await self._flush_locked(event.turn_id)

    async def _emit_chunk(self, turn_id: str, idx: int, chunk: AudioChunk) -> None:
        next_idx = self._next_idx.setdefault(turn_id, 0)
        if idx == next_idx:
            await self._flush_locked(turn_id)
            if self._next_idx.get(turn_id, 0) == idx:
                await self._bus.publish(chunk)
                return
        if idx > self._next_idx.get(turn_id, 0):
            self._buf.setdefault(turn_id, {}).setdefault(idx, []).append(chunk)

    async def _flush_locked(self, turn_id: str) -> None:
        buf = self._buf.setdefault(turn_id, {})
        done = self._done.setdefault(turn_id, set())
        self._next_idx.setdefault(turn_id, 0)
        while True:
            idx = self._next_idx[turn_id]
            if idx in done:
                for chunk in buf.pop(idx, []):
                    await self._bus.publish(chunk)
                done.discard(idx)
                self._next_idx[turn_id] = idx + 1
                continue
            pending = buf.pop(idx, [])
            for chunk in pending:
                await self._bus.publish(chunk)
            break

from __future__ import annotations

import asyncio

from asm.core.bus import EventBus
from asm.core.events import SentenceEnd, TextDelta, TurnAborted, TurnDone
from asm.core.interfaces import Clock, TurnRequest


class MockBrain:
    def __init__(self, bus: EventBus, clock: Clock) -> None:
        self._bus = bus
        self._clock = clock
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start_turn(self, req: TurnRequest) -> None:
        self._tasks[req.turn_id] = asyncio.create_task(self._run(req))

    async def cancel(self, turn_id: str) -> None:
        task = self._tasks.pop(turn_id, None)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    async def _run(self, req: TurnRequest) -> None:
        text = f"你刚才说：{req.text}。"
        try:
            for char in text:
                await self._clock.sleep(0.05)
                await self._bus.publish(TextDelta(turn_id=req.turn_id, text=char))
            await self._bus.publish(SentenceEnd(turn_id=req.turn_id, sentence_idx=0, text=text))
            await self._bus.publish(TurnDone(turn_id=req.turn_id))
        except asyncio.CancelledError:
            await self._bus.publish(TurnAborted(turn_id=req.turn_id, reason="cancel"))
            raise
        finally:
            self._tasks.pop(req.turn_id, None)

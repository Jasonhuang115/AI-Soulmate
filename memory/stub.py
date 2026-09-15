from __future__ import annotations

from asm.core.bus import EventBus
from asm.core.events import (
    ClientConnected,
    ClientDisconnected,
    CompressionNeeded,
    ContextReady,
    RecallRequested,
    SummaryReady,
    TurnClosed,
)
from asm.core.interfaces import Message, PromptContext
from memory.types import RecallContext, TurnRecord


class StubMemory:
    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        if bus is not None:
            bus.subscribe(RecallRequested, self._on_recall)
            bus.subscribe(TurnClosed, self._on_turn)
            bus.subscribe(CompressionNeeded, self._on_compress)
            bus.subscribe(ClientConnected, self._on_open)
            bus.subscribe(ClientDisconnected, self._on_close)

    async def recall(self, ctx: RecallContext, deadline_ms: int) -> PromptContext:
        del ctx, deadline_ms
        return PromptContext()

    async def observe(self, turn: TurnRecord) -> None:
        del turn

    async def compress(self, messages: list[Message]) -> str:
        del messages
        return ""

    async def on_session_start(self) -> PromptContext:
        return PromptContext()

    async def on_session_end(self) -> None:
        return None

    async def _on_recall(self, event: RecallRequested) -> None:
        if self._bus is None:
            return
        bundle = await self.recall(
            RecallContext(text=event.text, recent=event.recent, now_iso=""),
            event.deadline_ms,
        )
        await self._bus.publish(ContextReady(context=bundle))

    async def _on_turn(self, event: TurnClosed) -> None:
        await self.observe(
            TurnRecord(
                turn_id=event.turn_id,
                user_text=event.user_text,
                assistant_text=event.assistant_text,
                interrupted=event.interrupted,
            )
        )

    async def _on_compress(self, event: CompressionNeeded) -> None:
        if self._bus is None:
            return
        summary = await self.compress(list(event.messages))
        await self._bus.publish(SummaryReady(text=summary))

    async def _on_open(self, event: ClientConnected) -> None:
        del event
        if self._bus is None:
            return
        bundle = await self.on_session_start()
        await self._bus.publish(ContextReady(context=bundle))

    async def _on_close(self, event: ClientDisconnected) -> None:
        del event
        await self.on_session_end()

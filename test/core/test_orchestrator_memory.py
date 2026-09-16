import asyncio

from asm.core.bus import EventBus
from asm.core.clock import FakeClock
from asm.core.config import Settings
from asm.core.events import (
    ClientConnected,
    ClientDisconnected,
    CompressionNeeded,
    ContextReady,
    RecallRequested,
    SummaryReady,
    TextInput,
    TurnClosed,
    TurnDone,
)
from asm.core.interfaces import Message, PromptContext, TurnRequest
from asm.core.orchestrator import Orchestrator
from asm.core.session import Session
from memory_agent.types import RecallContext, TurnRecord


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

    async def compress(self, messages: list[Message], previous_summary: str = "") -> str:
        del messages, previous_summary
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
        summary = await self.compress(list(event.discarded), event.previous_summary)
        await self._bus.publish(SummaryReady(text=summary, drop_prefix=0))

    async def _on_open(self, event: ClientConnected) -> None:
        del event
        if self._bus is None:
            return
        bundle = await self.on_session_start()
        await self._bus.publish(ContextReady(context=bundle))

    async def _on_close(self, event: ClientDisconnected) -> None:
        del event
        await self.on_session_end()


class RecordingBrain:
    def __init__(self) -> None:
        self.starts: list[TurnRequest] = []

    async def start_turn(self, req: TurnRequest) -> None:
        self.starts.append(req)

    async def cancel(self, turn_id: str) -> None:
        del turn_id


class CompressingMemory(StubMemory):
    def __init__(self, bus) -> None:
        super().__init__(bus)
        self.calls = 0

    async def compress(self, messages: list[Message], previous_summary: str = "") -> str:
        del previous_summary
        self.calls += 1
        del messages
        return "互称：他叫我澄澄"


def _tiny() -> Settings:
    return Settings(context_window_tokens=80, context_reserve_ratio=0.15)


def _long_history() -> list[Message]:
    return [Message(role="user" if i % 2 == 0 else "assistant", content="x" * 40) for i in range(16)]


async def test_compression_updates_summary() -> None:
    bus = EventBus()
    session = Session()
    Orchestrator(bus, session, FakeClock(), RecordingBrain())
    CompressingMemory(bus)
    await bus.publish(
        CompressionNeeded(discarded=(Message(role="user", content="hi"),), previous_summary="")
    )
    assert session.session_summary == "互称：他叫我澄澄"


async def test_over_budget_after_turn_drops_and_summarizes() -> None:
    bus = EventBus()
    session = Session()
    brain = RecordingBrain()
    orch = Orchestrator(bus, session, FakeClock(), brain, settings=_tiny())
    orch._framework = ""
    memory = CompressingMemory(bus)
    session.messages = _long_history()
    await bus.publish(TextInput(text="hi"))
    await bus.publish(TurnDone(turn_id=brain.starts[0].turn_id))
    await asyncio.sleep(0.05)
    assert len(session.messages) < 17
    assert session.session_summary == "互称：他叫我澄澄"
    assert memory.calls >= 1


async def test_under_budget_does_not_compact() -> None:
    bus = EventBus()
    session = Session()
    brain = RecordingBrain()
    orch = Orchestrator(bus, session, FakeClock(), brain, settings=_tiny())
    orch._framework = ""
    memory = CompressingMemory(bus)
    await bus.publish(TextInput(text="hi"))
    await bus.publish(TurnDone(turn_id=brain.starts[0].turn_id))
    await asyncio.sleep(0.05)
    assert memory.calls == 0
    assert session.session_summary == ""


async def test_start_turn_hard_trims_before_brain() -> None:
    bus = EventBus()
    session = Session()
    brain = RecordingBrain()
    orch = Orchestrator(bus, session, FakeClock(), brain, settings=_tiny())
    orch._framework = ""
    session.messages = _long_history()
    CompressingMemory(bus)
    await bus.publish(TextInput(text="新"))
    assert len(brain.starts[0].messages) < 17
    assert len(session.messages) < 17


async def test_inflight_compact_does_not_run_twice() -> None:
    bus = EventBus()
    session = Session()
    brain = RecordingBrain()
    orch = Orchestrator(bus, session, FakeClock(), brain, settings=_tiny())
    orch._framework = ""
    gate = asyncio.Event()

    class SlowMemory(StubMemory):
        def __init__(self, event_bus) -> None:
            super().__init__(event_bus)
            self.calls = 0

        async def compress(self, messages: list[Message], previous_summary: str = "") -> str:
            del messages, previous_summary
            self.calls += 1
            await gate.wait()
            return "s"

    memory = SlowMemory(bus)
    session.messages = _long_history()
    await bus.publish(TextInput(text="一"))
    await bus.publish(TurnDone(turn_id=brain.starts[0].turn_id))
    await asyncio.sleep(0.05)
    session.messages = _long_history()
    await bus.publish(TextInput(text="二"))
    await bus.publish(TurnDone(turn_id=brain.starts[1].turn_id))
    await asyncio.sleep(0.05)
    assert memory.calls == 1
    gate.set()
    await asyncio.sleep(0.05)


async def test_disconnect_does_not_clear_window() -> None:
    bus = EventBus()
    session = Session()
    Orchestrator(bus, session, FakeClock(), RecordingBrain())
    StubMemory(bus)
    session.messages = [Message(role="user", content="还在")]
    session.session_summary = "互称：澄澄"
    await bus.publish(ClientDisconnected())
    assert session.messages[0].content == "还在"
    assert session.session_summary == "互称：澄澄"

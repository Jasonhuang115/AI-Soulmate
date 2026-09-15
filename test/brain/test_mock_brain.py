import asyncio

from asm.brain.mock import MockBrain
from asm.core.bus import EventBus
from asm.core.clock import FakeClock
from asm.core.events import TextDelta, TurnAborted, TurnDone
from asm.core.interfaces import PromptContext, TurnRequest


def _req(turn_id: str, text: str = "嗨") -> TurnRequest:
    return TurnRequest(
        turn_id=turn_id,
        text=text,
        speculative=False,
        context=PromptContext(),
        messages=(),
        session_summary="",
    )


async def test_mock_brain_streams_then_done() -> None:
    bus = EventBus()
    clock = FakeClock()
    brain = MockBrain(bus, clock)
    deltas: list[str] = []
    done: list[str] = []

    async def on_delta(event: TextDelta) -> None:
        deltas.append(event.text)

    async def on_done(event: TurnDone) -> None:
        done.append(event.turn_id)

    bus.subscribe(TextDelta, on_delta)
    bus.subscribe(TurnDone, on_done)

    await brain.start_turn(_req("t1"))
    await asyncio.sleep(0)
    await clock.advance(1.0)
    await asyncio.sleep(0)
    assert "".join(deltas) == "你刚才说：嗨。"
    assert done == ["t1"]


async def test_mock_brain_cancel_stops_deltas() -> None:
    bus = EventBus()
    clock = FakeClock()
    brain = MockBrain(bus, clock)
    deltas: list[str] = []
    aborted: list[str] = []

    async def on_delta(event: TextDelta) -> None:
        deltas.append(event.text)

    async def on_abort(event: TurnAborted) -> None:
        aborted.append(event.turn_id)

    bus.subscribe(TextDelta, on_delta)
    bus.subscribe(TurnAborted, on_abort)

    await brain.start_turn(_req("t2", "很长的一句话"))
    await asyncio.sleep(0)
    await clock.advance(0.05)
    await asyncio.sleep(0)
    before = len(deltas)
    await brain.cancel("t2")
    await clock.advance(2.0)
    await asyncio.sleep(0)
    assert len(deltas) == before
    assert aborted == ["t2"]

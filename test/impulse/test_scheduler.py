from datetime import datetime
from pathlib import Path

from asm.core.bus import EventBus
from asm.core.clock import FakeClock
from asm.core.events import DialogState, MicState, ProactiveTrigger, StateChanged
from asm.emotion.now import NowStore
from asm.impulse.scheduler import ImpulseScheduler


class Notes:
    def last_seen(self) -> datetime | None:
        return None

    def relationship_text(self) -> str:
        return ""

    def self_state_text(self) -> str:
        return ""


async def test_idle_fires_only_with_now(tmp_path: Path) -> None:
    bus = EventBus()
    clock = FakeClock()
    seen: list[ProactiveTrigger] = []

    async def capture(event: ProactiveTrigger) -> None:
        seen.append(event)

    bus.subscribe(ProactiveTrigger, capture)
    store = NowStore(tmp_path / "self_state.md")
    ImpulseScheduler(bus, clock, notes=Notes(), idle_s=10, cooldown_s=0, now_store=store)
    await bus.publish(MicState(open=True))
    await bus.publish(StateChanged(DialogState.IDLE))
    await clock.advance(10)
    assert seen == []

    store.commit("有点委屈，他刚才那句话", "t1", datetime.now())
    await bus.publish(StateChanged(DialogState.SPEAKING))
    await bus.publish(StateChanged(DialogState.IDLE))
    await clock.advance(10)
    assert len(seen) == 1
    assert seen[0].reason == "idle_companion"
    assert seen[0].hint == "有点委屈，他刚才那句话"

from datetime import datetime
from pathlib import Path

from asm.brain.prompt import format_situation
from asm.core.bus import EventBus
from asm.core.clock import FakeClock
from asm.core.events import (
    ClientConnected,
    ClientDisconnected,
    DialogState,
    TextInput,
    TurnDone,
)
from asm.core.interfaces import TurnRequest
from asm.core.orchestrator import Orchestrator
from asm.core.session import Session
from asm.emotion.now import NowStore


class RecordingBrain:
    def __init__(self) -> None:
        self.starts: list[TurnRequest] = []
        self.cancels: list[str] = []

    async def start_turn(self, req: TurnRequest) -> None:
        self.starts.append(req)

    async def cancel(self, turn_id: str) -> None:
        self.cancels.append(turn_id)


async def _harness(tmp_path: Path, wall: datetime):
    bus = EventBus()
    session = Session()
    brain = RecordingBrain()
    store = NowStore(tmp_path / "self_state.md")
    Orchestrator(
        bus,
        session,
        FakeClock(),
        brain,
        now_store=store,
        wall_now=lambda: wall,
    )
    return bus, session, brain, store


async def test_turn_done_commits_now(tmp_path: Path) -> None:
    wall = datetime(2026, 9, 17, 19, 41)
    bus, _session, brain, store = await _harness(tmp_path, wall)
    await bus.publish(TextInput("那句话过分了"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(TurnDone(turn_id=turn_id, raw_text="嗯。⟦sad⟧⟦此刻 有点委屈，他刚才那句话⟧"))
    assert store.mood is not None
    assert store.mood.text == "有点委屈，他刚才那句话"
    assert store.mood.source_turn == turn_id
    text = format_situation(wall, **store.situation_kwargs(wall))
    assert "你此刻：有点委屈，他刚才那句话（刚刚）" in text


async def test_interrupted_turn_does_not_commit(tmp_path: Path) -> None:
    wall = datetime(2026, 9, 17, 19, 41)
    bus, _session, brain, store = await _harness(tmp_path, wall)
    await bus.publish(TextInput("第一句"))
    await bus.publish(TextInput("第二句"))
    await bus.publish(TurnDone(turn_id=brain.starts[1].turn_id, raw_text="好。"))
    assert store.mood is None


async def test_same_day_reconnect_rewrites_then_clears(tmp_path: Path) -> None:
    wall = datetime(2026, 9, 17, 21, 0)
    bus, session, brain, store = await _harness(tmp_path, wall)
    store.commit("有点委屈，他刚才那句话", "old", datetime(2026, 9, 17, 19, 41))
    await bus.publish(ClientDisconnected())
    await bus.publish(ClientConnected())
    text = format_situation(wall, **store.situation_kwargs(wall))
    assert "上次分开时你：有点委屈，他刚才那句话" in text
    await bus.publish(TextInput("我回来了"))
    await bus.publish(TurnDone(turn_id=brain.starts[0].turn_id, raw_text="嗯。⟦happy⟧"))
    assert store.mood is None
    assert session.state == DialogState.IDLE


async def test_mid_speech_disconnect_fact(tmp_path: Path) -> None:
    wall = datetime(2026, 9, 17, 21, 0)
    bus, _session, brain, store = await _harness(tmp_path, wall)
    await bus.publish(TextInput("听我说"))
    assert brain.starts
    await bus.publish(ClientDisconnected())
    assert store.cut_pending
    await bus.publish(ClientConnected())
    text = format_situation(wall, **store.situation_kwargs(wall))
    assert "上次你说到一半，他断线了。" in text
    await bus.publish(TurnDone(turn_id=brain.starts[0].turn_id, raw_text="……"))
    assert store.cut_pending is False

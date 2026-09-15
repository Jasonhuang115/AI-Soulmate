from asm.core.bus import EventBus
from asm.core.clock import FakeClock
from asm.core.events import DialogState, ProactiveTrigger, SpeechStarted, TextInput, TurnDone
from asm.core.interfaces import TurnRequest
from asm.core.orchestrator import Orchestrator
from asm.core.session import Session


class RecordingBrain:
    def __init__(self) -> None:
        self.starts: list[TurnRequest] = []
        self.cancels: list[str] = []

    async def start_turn(self, req: TurnRequest) -> None:
        self.starts.append(req)

    async def cancel(self, turn_id: str) -> None:
        self.cancels.append(turn_id)


async def test_proactive_only_when_idle() -> None:
    bus = EventBus()
    session = Session()
    brain = RecordingBrain()
    Orchestrator(bus, session, FakeClock(), brain)
    await bus.publish(ProactiveTrigger("session_open", "距上次 3 小时"))
    assert len(brain.starts) == 1
    assert "主动" in brain.starts[0].text
    assert session.state == DialogState.THINKING
    await bus.publish(ProactiveTrigger("idle_companion", "再来一句"))
    assert len(brain.starts) == 1


async def test_user_cancels_proactive() -> None:
    bus = EventBus()
    session = Session()
    brain = RecordingBrain()
    Orchestrator(bus, session, FakeClock(), brain)
    await bus.publish(ProactiveTrigger("session_open", "hi"))
    first = brain.starts[0].turn_id
    await bus.publish(TextInput("我先说"))
    assert first in brain.cancels
    second = brain.starts[1].turn_id
    await bus.publish(TurnDone(turn_id=second))
    await bus.publish(ProactiveTrigger("idle_companion", "再来"))
    third = brain.starts[2].turn_id
    await bus.publish(SpeechStarted())
    assert third in brain.cancels
    assert session.state == DialogState.LISTENING

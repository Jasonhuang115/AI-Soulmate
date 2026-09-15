from asm.core.bus import EventBus
from asm.core.clock import FakeClock
from asm.core.events import Cancel, DialogState, SentenceEnd, StateChanged, TextInput, TurnDone
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


async def _harness() -> tuple[EventBus, Session, RecordingBrain, list[object]]:
    bus = EventBus()
    session = Session()
    brain = RecordingBrain()
    published: list[object] = []

    async def capture(event: object) -> None:
        published.append(event)

    bus.subscribe(Cancel, capture)
    bus.subscribe(StateChanged, capture)

    Orchestrator(
        bus=bus,
        session=session,
        clock=FakeClock(),
        brain=brain,
    )
    return bus, session, brain, published


async def test_text_input_starts_turn() -> None:
    bus, session, brain, published = await _harness()
    await bus.publish(TextInput(text="你好"))

    assert len(brain.starts) == 1
    assert brain.starts[0].text == "你好"
    assert brain.starts[0].speculative is False
    assert session.state == DialogState.THINKING
    assert any(isinstance(e, StateChanged) and e.state == DialogState.THINKING for e in published)
    assert session.messages[0].content == "你好"


async def test_second_text_cancels_first() -> None:
    bus, session, brain, published = await _harness()
    await bus.publish(TextInput(text="第一句"))
    first_id = brain.starts[0].turn_id
    await bus.publish(TextInput(text="第二句"))

    assert first_id in brain.cancels
    assert any(isinstance(e, Cancel) and e.turn_id == first_id for e in published)
    assert len(brain.starts) == 2
    assert brain.starts[1].text == "第二句"
    assert session.current_turn_id != first_id


async def test_stale_sentence_ignored() -> None:
    bus, session, brain, _published = await _harness()
    await bus.publish(TextInput(text="一"))
    first_id = session.current_turn_id
    assert first_id is not None
    await bus.publish(TextInput(text="二"))
    await bus.publish(SentenceEnd(turn_id=first_id, sentence_idx=0, text="旧句"))
    assert session.pending_sentences.get(first_id) == []
    assert session.current_turn_id != first_id
    assert session.pending_sentences[session.current_turn_id or ""] == []


async def test_turn_done_returns_idle() -> None:
    bus, session, brain, _published = await _harness()
    await bus.publish(TextInput(text="你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(TurnDone(turn_id=turn_id))
    assert session.state == DialogState.IDLE

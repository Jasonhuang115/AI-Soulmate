from asm.core.bus import EventBus
from asm.core.clock import FakeClock
from asm.core.events import AudioChunk, DialogState, LatencyMark, PlaybackDone, SentenceEnd, TextInput, TurnDone
from asm.core.interfaces import TurnRequest
from asm.core.orchestrator import Orchestrator
from asm.core.session import Session


class RecordingBrain:
    def __init__(self) -> None:
        self.starts: list[TurnRequest] = []

    async def start_turn(self, req: TurnRequest) -> None:
        self.starts.append(req)

    async def cancel(self, turn_id: str) -> None:
        del turn_id


async def test_first_audio_marks_speaking_and_latency() -> None:
    bus = EventBus()
    session = Session()
    marks: list[LatencyMark] = []

    async def on_latency(event: LatencyMark) -> None:
        marks.append(event)

    bus.subscribe(LatencyMark, on_latency)
    Orchestrator(bus, session, FakeClock(), RecordingBrain())
    await bus.publish(TextInput("你好"))
    turn_id = session.current_turn_id
    assert turn_id
    await bus.publish(SentenceEnd(turn_id=turn_id, sentence_idx=0, text="嗨。"))
    await bus.publish(
        AudioChunk(
            turn_id=turn_id,
            sentence_idx=0,
            seq=0,
            pcm16=b"\x00\x00",
            sample_rate=24000,
            mouth_energy=(0.0,),
        )
    )
    assert session.state == DialogState.SPEAKING
    await bus.publish(TurnDone(turn_id=turn_id))
    assert session.state == DialogState.SPEAKING
    await bus.publish(PlaybackDone(turn_id=turn_id))
    assert session.state == DialogState.IDLE
    assert marks and "t_first_audio" in marks[0].marks

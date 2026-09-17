from asm.core.bus import EventBus
from asm.core.clock import FakeClock
from asm.core.config import Settings
from asm.core.events import (
    AudioChunk,
    Cancel,
    ClientDisconnected,
    Commit,
    DialogState,
    Duck,
    MicState,
    PartialTranscript,
    PlaybackDone,
    SpeechEnded,
    SpeechStarted,
    SpokenProgress,
    StartTurn,
    StateChanged,
    TextInput,
    Unduck,
    UtteranceEnd,
)
from asm.core.interfaces import TurnRequest
from asm.core.orchestrator import Orchestrator, meaningful_len
from asm.core.session import Session


class RecordingBrain:
    def __init__(self) -> None:
        self.starts: list[TurnRequest] = []
        self.cancels: list[str] = []

    async def start_turn(self, req: TurnRequest) -> None:
        self.starts.append(req)

    async def cancel(self, turn_id: str) -> None:
        self.cancels.append(turn_id)


async def _harness() -> tuple[EventBus, Session, RecordingBrain, FakeClock, list[object]]:
    bus = EventBus()
    session = Session()
    brain = RecordingBrain()
    clock = FakeClock()
    published: list[object] = []

    async def capture(event: object) -> None:
        published.append(event)

    bus.subscribe(StateChanged, capture)
    bus.subscribe(StartTurn, capture)
    bus.subscribe(Commit, capture)
    bus.subscribe(Duck, capture)
    bus.subscribe(Unduck, capture)
    bus.subscribe(Cancel, capture)

    Orchestrator(bus, session, clock, brain)
    return bus, session, brain, clock, published


def _chunk(turn_id: str) -> AudioChunk:
    return AudioChunk(
        turn_id=turn_id,
        sentence_idx=0,
        seq=0,
        pcm16=b"\x00\x00",
        sample_rate=24000,
        mouth_energy=(0.0,),
    )


async def test_speech_started_goes_listening() -> None:
    bus, session, _brain, _clock, published = await _harness()
    await bus.publish(SpeechStarted())
    assert session.state == DialogState.LISTENING
    assert any(isinstance(e, StateChanged) and e.state == DialogState.LISTENING for e in published)


async def test_speech_ended_speculates_after_300ms() -> None:
    bus, session, brain, clock, published = await _harness()
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("今天天气怎么样"))
    await bus.publish(SpeechEnded())
    await clock.advance(0.3)
    assert session.state == DialogState.SPECULATING
    assert len(brain.starts) == 1
    assert brain.starts[0].speculative is True
    assert any(isinstance(e, StartTurn) and e.speculative for e in published)


async def test_commit_at_700ms() -> None:
    bus, session, brain, clock, published = await _harness()
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("今天天气怎么样"))
    await bus.publish(SpeechEnded())
    await clock.advance(0.3)
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    await clock.advance(0.4)
    assert any(isinstance(e, Commit) and e.turn_id == turn_id for e in published)
    assert session.state == DialogState.SPEAKING


async def test_speech_during_speculate_cancels() -> None:
    bus, session, brain, clock, _published = await _harness()
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("今天"))
    await bus.publish(SpeechEnded())
    await clock.advance(0.3)
    first = brain.starts[0].turn_id
    await bus.publish(SpeechStarted())
    assert first in brain.cancels
    assert session.state == DialogState.LISTENING
    await bus.publish(PartialTranscript("今天其实我想说另一件"))


async def test_speaking_speech_ducks() -> None:
    bus, session, brain, _clock, published = await _harness()
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    assert session.state == DialogState.SPEAKING
    await bus.publish(SpeechStarted())
    assert any(isinstance(e, Duck) for e in published)


async def test_barge_in_with_real_words() -> None:
    bus, session, brain, _clock, _published = await _harness()
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("等等"))
    assert turn_id in brain.cancels
    assert session.state == DialogState.LISTENING


async def test_barge_in_without_speech_ended_still_speculates() -> None:
    bus, session, brain, clock, published = await _harness()
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("等一下"))
    assert session.state == DialogState.LISTENING
    await clock.advance(0.2)
    assert session.state == DialogState.SPECULATING
    assert brain.starts[-1].text == "等一下"
    await clock.advance(0.3)
    assert any(isinstance(event, Commit) and event.turn_id == brain.starts[-1].turn_id for event in published)


async def test_barge_in_hmm_unducks() -> None:
    bus, session, brain, _clock, published = await _harness()
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("嗯"))
    await bus.publish(SpeechEnded())
    await bus.publish(UtteranceEnd("嗯"))
    assert turn_id not in brain.cancels
    assert session.state == DialogState.SPEAKING
    assert any(isinstance(e, Unduck) for e in published)


async def test_interrupt_keeps_spoken_only() -> None:
    bus, session, brain, _clock, _published = await _harness()
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    session.record_sentence(turn_id, 0, "前半句。")
    session.record_sentence(turn_id, 1, "后半句。")
    await bus.publish(SpokenProgress(turn_id=turn_id, sentence_idx=0))
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("停一下"))
    assert session.messages[-1].content == "前半句。 [被打断]"


def test_meaningful_len() -> None:
    assert meaningful_len("嗯") == 0
    assert meaningful_len("等等") == 2


async def test_stale_partial_does_not_self_interrupt() -> None:
    bus, session, brain, clock, published = await _harness()
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("今天天气怎么样"))
    await bus.publish(SpeechEnded())
    await clock.advance(0.3)
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    await clock.advance(0.4)
    assert session.state == DialogState.SPEAKING
    await bus.publish(SpeechStarted())
    await bus.publish(SpeechEnded())
    await bus.publish(UtteranceEnd(""))
    assert turn_id not in brain.cancels
    assert session.state == DialogState.SPEAKING
    assert any(isinstance(e, Unduck) for e in published)


async def test_barge_in_after_speech_ended_while_ducking() -> None:
    bus, session, brain, clock, _published = await _harness()
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    await bus.publish(SpeechStarted())
    await bus.publish(SpeechEnded())
    await bus.publish(UtteranceEnd("等等"))
    assert turn_id in brain.cancels
    assert session.state == DialogState.SPECULATING
    assert brain.starts[-1].speculative is True
    assert brain.starts[-1].text == "等等"


async def test_unduck_holdoff_ignores_echo() -> None:
    bus, session, brain, clock, published = await _harness()
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("嗯"))
    await bus.publish(SpeechEnded())
    await bus.publish(UtteranceEnd("嗯"))
    ducks = sum(isinstance(event, Duck) for event in published)
    await bus.publish(SpeechStarted())
    assert sum(isinstance(event, Duck) for event in published) == ducks
    assert turn_id not in brain.cancels
    await clock.advance(0.25)
    await bus.publish(SpeechStarted())
    assert sum(isinstance(event, Duck) for event in published) == ducks + 1


async def test_utterance_end_arms_timers_without_speech_ended() -> None:
    bus, session, brain, clock, _published = await _harness()
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("你好呀"))
    await bus.publish(UtteranceEnd("你好呀"))
    await clock.advance(0.3)
    assert session.state == DialogState.SPECULATING
    assert brain.starts[0].text == "你好呀"


async def test_partial_hang_sends_without_speech_ended() -> None:
    bus, session, brain, clock, _published = await _harness()
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("HELLO HELLO"))
    await clock.advance(1.2)
    assert session.state == DialogState.SPECULATING
    assert brain.starts[0].text == "HELLO HELLO"


async def test_vad_flicker_does_not_block_hang() -> None:
    bus, session, brain, clock, _published = await _harness()
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("HELLO HELLO"))
    await bus.publish(SpeechEnded())
    await bus.publish(SpeechStarted())
    await clock.advance(1.2)
    assert session.state == DialogState.SPECULATING
    assert brain.starts[0].text == "HELLO HELLO"


async def test_mic_close_sends_partial() -> None:
    bus, session, brain, clock, _published = await _harness()
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("HELLO HELLO"))
    await bus.publish(MicState(open=False))
    await clock.advance(0.3)
    assert session.state == DialogState.SPECULATING
    assert brain.starts[0].text == "HELLO HELLO"


async def test_single_char_waits_for_rest() -> None:
    bus, session, brain, clock, _published = await _harness()
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("你"))
    await bus.publish(SpeechEnded())
    await clock.advance(0.3)
    assert session.state == DialogState.LISTENING
    assert brain.starts == []
    await bus.publish(PartialTranscript("你好"))
    await clock.advance(0.3)
    assert session.state == DialogState.SPECULATING
    assert brain.starts[0].text == "你好"


async def test_single_char_sends_after_hang() -> None:
    bus, session, brain, clock, _published = await _harness()
    await bus.publish(SpeechStarted())
    await bus.publish(PartialTranscript("你"))
    await bus.publish(SpeechEnded())
    await clock.advance(1.2)
    assert session.state == DialogState.SPECULATING
    assert brain.starts[0].text == "你"


async def test_barge_in_duration_without_transcript() -> None:
    bus, session, brain, clock, _published = await _harness()
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    await bus.publish(SpeechStarted())
    await clock.advance(0.5)
    assert turn_id in brain.cancels
    assert session.state == DialogState.LISTENING


async def test_turn_done_waits_for_playback() -> None:
    bus, session, brain, _clock, _published = await _harness()
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    from asm.core.events import TurnDone

    await bus.publish(TurnDone(turn_id=turn_id))
    assert session.state == DialogState.SPEAKING
    await bus.publish(PlaybackDone(turn_id=turn_id))
    assert session.state == DialogState.IDLE


async def test_playback_watchdog_idles_if_done_lost() -> None:
    bus = EventBus()
    session = Session()
    brain = RecordingBrain()
    clock = FakeClock()
    Orchestrator(bus, session, clock, brain, Settings(playback_watchdog_slack_ms=100))
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    from asm.core.events import TurnDone

    await bus.publish(TurnDone(turn_id=turn_id))
    assert session.state == DialogState.SPEAKING
    await clock.advance(0.2)
    assert session.state == DialogState.IDLE


async def test_disconnect_finalizes_speaking_turn() -> None:
    bus, session, brain, _clock, _published = await _harness()
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    from asm.core.events import TurnDone

    await bus.publish(TurnDone(turn_id=turn_id, raw_text="嗨"))
    await bus.publish(ClientDisconnected())
    assert session.state == DialogState.IDLE
    assert session.messages[-1].content == "嗨"


async def test_late_audio_after_playback_done_keeps_speaking() -> None:
    bus, session, brain, _clock, _published = await _harness()
    await bus.publish(TextInput("你好"))
    turn_id = brain.starts[0].turn_id
    await bus.publish(_chunk(turn_id))
    from asm.core.events import TurnDone

    await bus.publish(PlaybackDone(turn_id=turn_id))
    await bus.publish(_chunk(turn_id))
    await bus.publish(TurnDone(turn_id=turn_id))
    assert session.state == DialogState.SPEAKING
    await bus.publish(PlaybackDone(turn_id=turn_id))
    assert session.state == DialogState.IDLE


async def test_text_during_playback_interrupts() -> None:
    bus, session, brain, _clock, published = await _harness()
    await bus.publish(TextInput("你好"))
    first = brain.starts[0].turn_id
    await bus.publish(_chunk(first))
    await bus.publish(TextInput("下一句"))
    assert first in brain.cancels
    assert any(isinstance(e, Cancel) for e in published)
    assert brain.starts[1].text == "下一句"

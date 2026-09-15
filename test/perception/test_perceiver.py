from asm.core.bus import EventBus
from asm.core.events import (
    DialogState,
    Duck,
    MicState,
    PartialTranscript,
    SpeechEnded,
    SpeechStarted,
    StateChanged,
    UtteranceEnd,
)
from asm.perception.service import SpeechPerceiver


class StubVad:
    def __init__(self) -> None:
        self.n = 0

    def feed(self, samples: list[float]) -> list[str]:
        del samples
        self.n += 1
        if self.n == 1:
            return ["start"]
        if self.n == 2:
            return ["end"]
        return []


class StubAsr:
    def feed(self, samples: list[float]) -> str | None:
        del samples
        return "你好"

    def finalize(self) -> str:
        return "你好"


async def test_perceiver_publishes_vad_and_asr() -> None:
    bus = EventBus()
    events: list[object] = []

    async def capture(event: object) -> None:
        events.append(event)

    bus.subscribe(SpeechStarted, capture)
    bus.subscribe(SpeechEnded, capture)
    bus.subscribe(PartialTranscript, capture)
    bus.subscribe(UtteranceEnd, capture)

    perceiver = SpeechPerceiver(bus, StubVad(), StubAsr())
    await perceiver.feed(b"\x00\x00" * 320)
    await perceiver.feed(b"\x00\x00" * 320)
    kinds = [type(e).__name__ for e in events]
    assert "SpeechStarted" in kinds
    assert "PartialTranscript" in kinds
    assert "SpeechEnded" in kinds
    assert "UtteranceEnd" in kinds
    assert perceiver.listening


def test_perceiver_listening_requires_both_engines() -> None:
    bus = EventBus()
    assert SpeechPerceiver(bus, None, None).listening is False
    assert SpeechPerceiver(bus, StubVad(), None).listening is False
    assert SpeechPerceiver(bus, None, StubAsr()).listening is False
    assert SpeechPerceiver(bus, StubVad(), StubAsr()).listening is True


class CountingAsr:
    def __init__(self) -> None:
        self.feeds = 0
        self.resets = 0
        self._last = ""

    def feed(self, samples: list[float]) -> str | None:
        del samples
        self.feeds += 1
        self._last = f"字{self.feeds}"
        return self._last

    def reset(self) -> None:
        self.resets += 1
        self._last = ""

    def finalize(self) -> str:
        text = self._last
        self._last = ""
        return text


async def test_perceiver_pauses_asr_while_speaking() -> None:
    bus = EventBus()
    events: list[object] = []

    async def capture(event: object) -> None:
        events.append(event)

    bus.subscribe(PartialTranscript, capture)
    asr = CountingAsr()
    perceiver = SpeechPerceiver(bus, StubVad(), asr)
    await perceiver.feed(b"\x00\x00" * 320)
    n = sum(isinstance(event, PartialTranscript) for event in events)
    assert n == 1
    await bus.publish(StateChanged(DialogState.SPEAKING))
    await perceiver.feed(b"\x00\x00" * 320)
    assert sum(isinstance(event, PartialTranscript) for event in events) == n
    assert asr.resets >= 1
    await bus.publish(Duck())
    await perceiver.feed(b"\x00\x00" * 320)
    assert sum(isinstance(event, PartialTranscript) for event in events) == n + 1


class StickyVad:
    def feed(self, samples: list[float]) -> list[str]:
        del samples
        if not hasattr(self, "started"):
            self.started = True
            return ["start"]
        return []


async def test_perceiver_energy_silence_ends_sticky_vad() -> None:
    bus = EventBus()
    events: list[object] = []

    async def capture(event: object) -> None:
        events.append(event)

    bus.subscribe(SpeechEnded, capture)
    bus.subscribe(UtteranceEnd, capture)
    perceiver = SpeechPerceiver(bus, StickyVad(), StubAsr())
    await perceiver.feed(b"\x00\x00" * 320)
    for _ in range(60):
        await perceiver.feed(b"\x00\x00" * 320)
    kinds = [type(event).__name__ for event in events]
    assert "SpeechEnded" in kinds
    assert "UtteranceEnd" in kinds


async def test_perceiver_flush_on_mic_close() -> None:
    bus = EventBus()
    events: list[object] = []

    async def capture(event: object) -> None:
        events.append(event)

    bus.subscribe(SpeechEnded, capture)
    bus.subscribe(UtteranceEnd, capture)
    perceiver = SpeechPerceiver(bus, StubVad(), StubAsr())
    await perceiver.feed(b"\x00\x00" * 320)
    await bus.publish(MicState(open=False))
    kinds = [type(event).__name__ for event in events]
    assert "SpeechEnded" in kinds
    assert "UtteranceEnd" in kinds

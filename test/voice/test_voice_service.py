import asyncio

from asm.core.bus import EventBus
from asm.core.events import AudioChunk, SentenceEnd
from asm.voice.service import VoiceService


class ReorderTTS:
    async def synthesize(self, turn_id: str, sentence_idx: int, text: str):
        del text
        if sentence_idx == 0:
            await asyncio.sleep(0.05)
        yield AudioChunk(
            turn_id=turn_id,
            sentence_idx=sentence_idx,
            seq=0,
            pcm16=b"\x00\x00",
            sample_rate=24000,
            mouth_energy=(0.0,),
        )

    async def cancel(self, turn_id: str) -> None:
        del turn_id


async def test_voice_publishes_in_sentence_order() -> None:
    bus = EventBus()
    VoiceService(bus, ReorderTTS())
    seen: list[int] = []

    async def on_audio(event: AudioChunk) -> None:
        seen.append(event.sentence_idx)

    bus.subscribe(AudioChunk, on_audio)
    await bus.publish(SentenceEnd(turn_id="t", sentence_idx=0, text="一。"))
    await bus.publish(SentenceEnd(turn_id="t", sentence_idx=1, text="二。"))
    await asyncio.sleep(0.1)
    assert seen == [0, 1]


class StreamingTTS:
    async def synthesize(self, turn_id: str, sentence_idx: int, text: str):
        del turn_id, sentence_idx, text
        yield AudioChunk(
            turn_id="t",
            sentence_idx=0,
            seq=0,
            pcm16=b"\x01\x00",
            sample_rate=24000,
            mouth_energy=(0.0,),
        )
        await asyncio.sleep(0.05)
        yield AudioChunk(
            turn_id="t",
            sentence_idx=0,
            seq=1,
            pcm16=b"\x02\x00",
            sample_rate=24000,
            mouth_energy=(0.0,),
        )

    async def cancel(self, turn_id: str) -> None:
        del turn_id


async def test_voice_streams_chunks_before_sentence_finishes() -> None:
    bus = EventBus()
    VoiceService(bus, StreamingTTS())
    seqs: list[int] = []

    async def on_audio(event: AudioChunk) -> None:
        seqs.append(event.seq)

    bus.subscribe(AudioChunk, on_audio)
    await bus.publish(SentenceEnd(turn_id="t", sentence_idx=0, text="一。"))
    await asyncio.sleep(0.01)
    assert seqs == [0]
    await asyncio.sleep(0.06)
    assert seqs == [0, 1]

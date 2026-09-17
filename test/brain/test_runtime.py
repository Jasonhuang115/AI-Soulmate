import asyncio

from asm.brain.deepseek_client import ScriptedStreamer, TokenEvent
from asm.brain.runtime import FALLBACK_SENTENCE, BrainRuntime
from asm.core.bus import EventBus
from asm.core.clock import FakeClock
from asm.core.events import SentenceEnd, ToolCall, TurnAborted, TurnDone
from asm.core.interfaces import PromptContext, TurnRequest
from asm.core.config import Settings


def _req(text: str = "你好") -> TurnRequest:
    return TurnRequest(
        turn_id="t1",
        text=text,
        speculative=False,
        context=PromptContext(),
        messages=(),
        session_summary="",
    )


async def test_runtime_splits_sentences() -> None:
    bus = EventBus()
    sentences: list[str] = []
    done: list[str] = []

    async def on_sentence(event: SentenceEnd) -> None:
        sentences.append(event.text)

    async def on_done(event: TurnDone) -> None:
        done.append(event.turn_id)

    bus.subscribe(SentenceEnd, on_sentence)
    bus.subscribe(TurnDone, on_done)
    runtime = BrainRuntime(
        bus,
        FakeClock(),
        ScriptedStreamer([TokenEvent(kind="text", text="你好。今天不错。")]),
    )
    await runtime.start_turn(_req())
    await asyncio.sleep(0.05)
    assert sentences == ["你好。", "今天不错。"]
    assert done == ["t1"]


async def test_runtime_cancel_aborts() -> None:
    bus = EventBus()
    clock = FakeClock()
    aborted: list[str] = []
    sentences: list[str] = []

    async def on_abort(event: TurnAborted) -> None:
        aborted.append(event.turn_id)

    async def on_sentence(event: SentenceEnd) -> None:
        sentences.append(event.text)

    bus.subscribe(TurnAborted, on_abort)
    bus.subscribe(SentenceEnd, on_sentence)
    runtime = BrainRuntime(
        bus,
        clock,
        ScriptedStreamer(
            [
                TokenEvent(kind="text", text="第一句。"),
                TokenEvent(kind="text", text="不该出现的第二句。"),
            ],
            delay_s=0.2,
            clock=clock,
        ),
    )
    await runtime.start_turn(_req())
    await asyncio.sleep(0)
    await clock.advance(0.2)
    await asyncio.sleep(0)
    await runtime.cancel("t1")
    await clock.advance(1.0)
    await asyncio.sleep(0)
    assert aborted == ["t1"]
    assert "不该出现的第二句。" not in sentences


async def test_runtime_fallback_after_timeout() -> None:
    bus = EventBus()
    clock = FakeClock()
    sentences: list[str] = []

    async def on_sentence(event: SentenceEnd) -> None:
        sentences.append(event.text)

    bus.subscribe(SentenceEnd, on_sentence)

    class SlowStreamer:
        async def stream_chat(self, messages, tools, cancel_event):
            del messages, tools
            await clock.sleep(20)
            if cancel_event.is_set():
                return
            yield TokenEvent(kind="text", text="太慢了。")

    runtime = BrainRuntime(
        bus,
        clock,
        SlowStreamer(),
        settings=Settings(first_token_timeout_s=5),
    )
    await runtime.start_turn(_req())
    for _ in range(30):
        await asyncio.sleep(0)
        await clock.advance(1)
        if sentences:
            break
    assert FALLBACK_SENTENCE in "".join(sentences)


async def test_runtime_emo_aligns_to_sentence_and_strips_tts_text() -> None:
    bus = EventBus()
    sentences: list[SentenceEnd] = []
    calls: list[ToolCall] = []

    async def on_sentence(event: SentenceEnd) -> None:
        sentences.append(event)

    async def on_tool(event: ToolCall) -> None:
        calls.append(event)

    bus.subscribe(SentenceEnd, on_sentence)
    bus.subscribe(ToolCall, on_tool)
    runtime = BrainRuntime(
        bus,
        FakeClock(),
        ScriptedStreamer([TokenEvent(kind="text", text="你好。⟦happy⟧")]),
    )
    await runtime.start_turn(_req())
    await asyncio.sleep(0.05)
    assert sentences
    assert all("⟦" not in item.text and "[emo=" not in item.text for item in sentences)
    emo_calls = [item for item in calls if item.name == "set_emotion"]
    assert emo_calls
    assert emo_calls[0].arguments["emotion"] == "happy"
    assert emo_calls[0].sentence_idx == sentences[0].sentence_idx


async def test_runtime_motion_override_on_same_sentence() -> None:
    bus = EventBus()
    calls: list[ToolCall] = []

    async def on_tool(event: ToolCall) -> None:
        calls.append(event)

    bus.subscribe(ToolCall, on_tool)
    runtime = BrainRuntime(
        bus,
        FakeClock(),
        ScriptedStreamer([TokenEvent(kind="text", text="嗨。⟦playful⟧⟦wave⟧")]),
    )
    await runtime.start_turn(_req())
    await asyncio.sleep(0.05)
    emo_calls = [item for item in calls if item.name == "set_emotion"]
    assert emo_calls
    assert emo_calls[0].arguments == {"emotion": "playful", "motions": ["wave"]}


async def test_runtime_leading_motion_is_immediate() -> None:
    bus = EventBus()
    calls: list[ToolCall] = []

    async def on_tool(event: ToolCall) -> None:
        calls.append(event)

    bus.subscribe(ToolCall, on_tool)
    runtime = BrainRuntime(
        bus,
        FakeClock(),
        ScriptedStreamer([TokenEvent(kind="text", text="⟦wave⟧好。⟦happy⟧")]),
    )
    await runtime.start_turn(_req())
    await asyncio.sleep(0.05)
    emo_calls = [item for item in calls if item.name == "set_emotion"]
    assert emo_calls[0].arguments == {"motions": ["wave"], "immediate": True}
    assert emo_calls[1].arguments == {"emotion": "happy"}


async def test_runtime_turn_done_keeps_raw_markers() -> None:
    bus = EventBus()
    sentences: list[str] = []
    raw: list[str] = []

    async def on_sentence(event: SentenceEnd) -> None:
        sentences.append(event.text)

    async def on_done(event: TurnDone) -> None:
        raw.append(event.raw_text)

    bus.subscribe(SentenceEnd, on_sentence)
    bus.subscribe(TurnDone, on_done)
    runtime = BrainRuntime(
        bus,
        FakeClock(),
        ScriptedStreamer([TokenEvent(kind="text", text="⟦wave⟧好。⟦happy⟧")]),
    )
    await runtime.start_turn(_req())
    await asyncio.sleep(0.05)
    assert sentences == ["好。"]
    assert raw == ["⟦wave⟧好。⟦happy⟧"]


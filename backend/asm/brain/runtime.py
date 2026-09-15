from __future__ import annotations

import asyncio
import json
from datetime import datetime

from asm.brain.prompt import build_messages, format_situation, resolve_prompts_dir
from asm.brain.sentences import SentenceSplitter
from asm.core.bus import EventBus
from asm.core.config import Settings
from asm.brain.tool_parser import EmotionStripper, Marker, group_markers
from asm.core.events import SentenceEnd, TextDelta, ToolCall, TurnAborted, TurnDone
from asm.core.interfaces import Clock, Message, ToolSpec, TurnRequest
from asm.brain.deepseek_client import ChatStreamer, TokenEvent


FALLBACK_SENTENCE = "我想想……"


class BrainRuntime:
    def __init__(
        self,
        bus: EventBus,
        clock: Clock,
        client: ChatStreamer,
        settings: Settings | None = None,
        tools: list[ToolSpec] | None = None,
        now_fn=datetime.now,
    ) -> None:
        self._bus = bus
        self._clock = clock
        self._client = client
        self._settings = settings or Settings()
        self._tools = tools or []
        self._now_fn = now_fn
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancels: dict[str, asyncio.Event] = {}

    async def start_turn(self, req: TurnRequest) -> None:
        cancel = asyncio.Event()
        self._cancels[req.turn_id] = cancel
        self._tasks[req.turn_id] = asyncio.create_task(self._run(req, cancel))

    async def cancel(self, turn_id: str) -> None:
        event = self._cancels.get(turn_id)
        if event is not None:
            event.set()
        task = self._tasks.pop(turn_id, None)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    async def _run(self, req: TurnRequest, cancel: asyncio.Event) -> None:
        try:
            situation = format_situation(self._now_fn())
            history = req.messages
            if history and history[-1].role == "user" and history[-1].content == req.text:
                history = history[:-1]
            messages = build_messages(
                context=req.context,
                session_summary=req.session_summary,
                situation=situation,
                history=history,
                user_text=req.text,
                prompts_dir=resolve_prompts_dir(self._settings.prompts_dir),
            )
            ok = await self._stream_live(req.turn_id, messages, cancel)
            if cancel.is_set():
                await self._bus.publish(TurnAborted(turn_id=req.turn_id, reason="cancel"))
                return
            if not ok:
                emitter = _TurnEmitter(self._bus, req.turn_id, self._settings)
                await emitter.consume(TokenEvent(kind="text", text=FALLBACK_SENTENCE))
                await emitter.finish()
        except asyncio.CancelledError:
            await self._bus.publish(TurnAborted(turn_id=req.turn_id, reason="cancel"))
            raise
        finally:
            self._tasks.pop(req.turn_id, None)
            self._cancels.pop(req.turn_id, None)

    async def _stream_live(
        self, turn_id: str, messages: list[Message], cancel: asyncio.Event
    ) -> bool:
        for _attempt in range(2):
            agen = self._client.stream_chat(messages, self._tools, cancel)
            first = await self._first_token(agen, cancel)
            if cancel.is_set():
                return True
            if first is None:
                continue
            emitter = _TurnEmitter(self._bus, turn_id, self._settings)
            await emitter.consume(first)
            async for event in agen:
                if cancel.is_set():
                    return True
                await emitter.consume(event)
            await emitter.finish()
            return True
        return False

    async def _first_token(
        self, agen, cancel: asyncio.Event
    ) -> TokenEvent | None:
        first_task = asyncio.create_task(agen.__anext__())  # type: ignore[arg-type]
        timeout_task = asyncio.create_task(self._clock.sleep(self._settings.first_token_timeout_s))
        done, _pending = await asyncio.wait(
            {first_task, timeout_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if cancel.is_set():
            first_task.cancel()
            timeout_task.cancel()
            return None
        if timeout_task in done and first_task not in done:
            first_task.cancel()
            try:
                await first_task
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
            except RuntimeError:
                pass
            return None
        timeout_task.cancel()
        try:
            return first_task.result()
        except StopAsyncIteration:
            return TokenEvent(kind="text", text="")

class _TurnEmitter:
    def __init__(self, bus: EventBus, turn_id: str, settings: Settings) -> None:
        self._bus = bus
        self._turn_id = turn_id
        self._splitter = SentenceSplitter(
            first_min_chars=settings.first_min_chars,
            later_min_chars=settings.later_min_chars,
        )
        self._sentence_idx = 0
        self._tool_args: dict[str, str] = {}
        self._tool_names: dict[str, str] = {}
        self._emo = EmotionStripper()

    async def consume(self, event: TokenEvent) -> None:
        if event.kind == "text" and event.text:
            cleaned, markers = self._emo.feed(event.text)
            await self._on_cleaned(cleaned, markers)
        elif event.kind == "tool":
            key = event.tool_id or event.tool_name or "0"
            if event.tool_name:
                self._tool_names[key] = event.tool_name
            if event.tool_arguments:
                self._tool_args[key] = self._tool_args.get(key, "") + event.tool_arguments

    async def finish(self) -> None:
        cleaned, markers = self._emo.flush()
        await self._on_cleaned(cleaned, markers)
        for key, raw in self._tool_args.items():
            try:
                arguments = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                arguments = {"_raw": raw}
            await self._bus.publish(
                ToolCall(
                    turn_id=self._turn_id,
                    sentence_idx=max(self._sentence_idx - 1, 0),
                    name=self._tool_names.get(key, ""),
                    arguments=arguments if isinstance(arguments, dict) else {"value": arguments},
                )
            )
        tail = self._splitter.flush()
        if tail:
            await self._bus.publish(
                SentenceEnd(turn_id=self._turn_id, sentence_idx=self._sentence_idx, text=tail)
            )
        await self._bus.publish(TurnDone(turn_id=self._turn_id))

    async def _on_cleaned(self, cleaned: str, markers: list[Marker]) -> None:
        if cleaned:
            await self._bus.publish(TextDelta(turn_id=self._turn_id, text=cleaned))
        groups = group_markers(markers)
        sentences = self._splitter.feed(cleaned) if cleaned else []
        if sentences:
            for i, sentence in enumerate(sentences):
                idx = self._sentence_idx
                if i < len(groups):
                    await self._avatar(idx, groups[i][0], groups[i][1])
                await self._bus.publish(
                    SentenceEnd(turn_id=self._turn_id, sentence_idx=idx, text=sentence)
                )
                self._sentence_idx += 1
            for emotion, motion in groups[len(sentences) :]:
                await self._avatar(max(self._sentence_idx - 1, 0), emotion, motion)
            return
        for emotion, motion in groups:
            await self._avatar(max(self._sentence_idx - 1, 0), emotion, motion)

    async def _avatar(self, sentence_idx: int, emotion: str | None, motion: str | None) -> None:
        arguments: dict[str, str] = {}
        if emotion:
            arguments["emotion"] = emotion
        if motion:
            arguments["motion"] = motion
        if not arguments:
            return
        await self._bus.publish(
            ToolCall(
                turn_id=self._turn_id,
                sentence_idx=sentence_idx,
                name="set_emotion",
                arguments=arguments,
            )
        )

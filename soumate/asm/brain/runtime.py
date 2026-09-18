from __future__ import annotations

import asyncio
import json
from datetime import datetime

from asm.brain.prompt import build_messages, format_situation, resolve_prompts_dir
from asm.brain.sentences import SentenceSplitter
from asm.core.bus import EventBus
from asm.core.config import Settings
from asm.brain.tool_parser import EmotionStripper, Marker, TagSet, collect_tags
from asm.core.events import SentenceEnd, TextDelta, ToolCall, TurnAborted, TurnDone
from asm.core.interfaces import Clock, Message, ToolSpec, TurnRequest
from asm.brain.deepseek_client import ChatStreamer, TokenEvent
from asm.emotion.now import NowStore


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
        now_store: NowStore | None = None,
        last_chat_fn=None,
    ) -> None:
        self._bus = bus
        self._clock = clock
        self._client = client
        self._settings = settings or Settings()
        self._tools = tools or []
        self._now_fn = now_fn
        self._now_store = now_store
        self._last_chat_fn = last_chat_fn
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
            now = self._now_fn()
            extras = self._now_store.situation_kwargs(now) if self._now_store else {}
            last_chat = self._last_chat_fn() if self._last_chat_fn else None
            situation = format_situation(
                now,
                last_chat_at=last_chat,
                now_mood=extras.get("now_mood"),  # type: ignore[arg-type]
                reunion=bool(extras.get("reunion")),
                mid_speech_cut=bool(extras.get("mid_speech_cut")),
            )
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
        self._has_open_text = False
        self._last_ended_idx: int | None = None
        self._pending_lead: list[Marker] = []
        self._pending_after_end: list[Marker] = []
        self._pending_trail: list[Marker] = []
        self._raw_parts: list[str] = []

    async def consume(self, event: TokenEvent) -> None:
        if event.kind == "text" and event.text:
            self._raw_parts.append(event.text)
            await self._on_parts(self._emo.feed_parts(event.text))
            await self._flush_turn_start()
        elif event.kind == "tool":
            key = event.tool_id or event.tool_name or "0"
            if event.tool_name:
                self._tool_names[key] = event.tool_name
            if event.tool_arguments:
                self._tool_args[key] = self._tool_args.get(key, "") + event.tool_arguments

    async def finish(self) -> None:
        await self._on_parts(self._emo.flush_parts())
        await self._flush_turn_start()
        if self._pending_after_end:
            idx = self._last_ended_idx if self._last_ended_idx is not None else max(self._sentence_idx - 1, 0)
            await self._emit_tags(collect_tags(self._pending_after_end), idx, immediate=False)
            self._pending_after_end = []
        if self._pending_trail:
            await self._emit_tags(
                collect_tags(self._pending_trail),
                self._sentence_idx if self._has_open_text else max(self._sentence_idx - 1, 0),
                immediate=False,
            )
            self._pending_trail = []
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
        await self._bus.publish(
            TurnDone(turn_id=self._turn_id, raw_text="".join(self._raw_parts))
        )

    async def _on_parts(self, parts: list[str | Marker]) -> None:
        for part in parts:
            if isinstance(part, Marker):
                await self._on_marker(part)
            elif part:
                await self._on_text(part)

    async def _on_marker(self, marker: Marker) -> None:
        if marker.kind == "now":
            return
        if self._has_open_text:
            self._pending_trail.append(marker)
            return
        if self._last_ended_idx is None:
            self._pending_lead.append(marker)
            return
        self._pending_after_end.append(marker)

    async def _on_text(self, text: str) -> None:
        if self._pending_lead:
            await self._emit_tags(collect_tags(self._pending_lead), self._sentence_idx, immediate=True)
            self._pending_lead = []
        if self._pending_after_end:
            await self._emit_tags(collect_tags(self._pending_after_end), self._sentence_idx, immediate=True)
            self._pending_after_end = []
        await self._bus.publish(TextDelta(turn_id=self._turn_id, text=text))
        self._has_open_text = True
        for sentence in self._splitter.feed(text):
            await self._emit_tags(collect_tags(self._pending_trail), self._sentence_idx, immediate=False)
            self._pending_trail = []
            await self._bus.publish(
                SentenceEnd(turn_id=self._turn_id, sentence_idx=self._sentence_idx, text=sentence)
            )
            self._last_ended_idx = self._sentence_idx
            self._sentence_idx += 1
            self._has_open_text = False

    async def _flush_turn_start(self) -> None:
        if self._pending_lead and self._last_ended_idx is None:
            await self._emit_tags(collect_tags(self._pending_lead), self._sentence_idx, immediate=True)
            self._pending_lead = []

    async def _emit_tags(self, tags: TagSet, sentence_idx: int, immediate: bool) -> None:
        if tags.empty:
            return
        arguments: dict[str, object] = {}
        if tags.emotion:
            arguments["emotion"] = tags.emotion
        if tags.motions:
            arguments["motions"] = list(tags.motions)
        if tags.control:
            arguments["control"] = tags.control
        if immediate:
            arguments["immediate"] = True
        await self._bus.publish(
            ToolCall(
                turn_id=self._turn_id,
                sentence_idx=sentence_idx,
                name="set_emotion",
                arguments=arguments,
            )
        )

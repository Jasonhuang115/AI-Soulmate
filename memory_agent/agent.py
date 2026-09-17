from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from asm.brain.compact import clip_summary, heuristic_summary
from asm.brain.prompt import default_prompts_dir
from asm.core.bus import EventBus
from asm.core.events import (
    ClientConnected,
    ClientDisconnected,
    CompressionNeeded,
    ContextReady,
    RecallRequested,
    SummaryReady,
    TurnClosed,
)
from asm.core.interfaces import Message, PromptContext

from .store.gate import DreamGate
from .store.paths import default_memdir, read_last_seen
from .store.tools import TYPE_FILES, MemoryTools, normalize_rel
from .store.turns import TurnStore
from .types import MemoryLLM, RecallContext, TurnRecord

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

CONSOLIDATE_TOOLS = ("search_turns", "ls", "read", "grep", "write", "write_section")
CONSOLIDATE_STEPS = 20


def _fn(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required if required is not None else list(properties),
            },
        },
    }


TOOL_SPECS: dict[str, dict[str, Any]] = {
    "ls": _fn(
        "ls",
        "List files under the memory directory.",
        {"rel": {"type": "string", "description": "Relative path, default ."}},
        required=[],
    ),
    "read": _fn("read", "Read a memory file.", {"rel": {"type": "string"}}),
    "grep": _fn(
        "grep",
        "Search memory files. Returns path:line:text hits, max 50.",
        {
            "pattern": {"type": "string"},
            "rel": {"type": "string", "description": "Relative path, default ."},
        },
        required=["pattern"],
    ),
    "write": _fn(
        "write",
        "Replace a writable memory file. MEMORY.md only after a type file this run; max 200 lines / 25KB.",
        {"rel": {"type": "string"}, "content": {"type": "string"}},
    ),
    "write_section": _fn(
        "write_section",
        "Replace one markdown ## section in a writable memory file.",
        {
            "rel": {"type": "string"},
            "heading": {"type": "string"},
            "body": {"type": "string"},
        },
    ),
    "search_turns": _fn(
        "search_turns",
        "Search conversation turns in SQLite. Time, keyword, and speaker filters. Read-only.",
        {
            "pattern": {
                "type": "string",
                "description": "Optional substring, case-insensitive. Empty means time-only.",
            },
            "since": {
                "type": "string",
                "description": "Inclusive ISO start, e.g. 2026-09-15T17:46:00",
            },
            "until": {
                "type": "string",
                "description": "Exclusive ISO end",
            },
            "day": {
                "type": "string",
                "description": "YYYY-MM-DD; intersects since/until if both set",
            },
            "field": {
                "type": "string",
                "description": "user | assistant | both (default both). Only affects pattern.",
            },
            "n": {
                "type": "integer",
                "description": "Max rows, default 20, cap 500",
            },
            "order": {
                "type": "string",
                "description": "asc | desc (default desc). Use asc when scanning since last_run.",
            },
        },
        required=[],
    ),
}


def load_prompt() -> str:
    soul = (default_prompts_dir() / "01-soul.md").read_text(encoding="utf-8").strip()
    shared = (PROMPTS_DIR / "agent.md").read_text(encoding="utf-8").strip()
    body = (PROMPTS_DIR / "consolidate.md").read_text(encoding="utf-8").strip()
    return (
        "只读人设（Soul，不是记忆，你不能改）：\n"
        f"{soul}\n\n"
        f"{shared}\n\n{body}"
    )


def _parse_args(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _dump(result: object) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False)


class TextCompleter(Protocol):
    async def complete(self, messages: list[Message]) -> str: ...


class MemoryAgent:
    def __init__(
        self,
        root: Path | None = None,
        client: MemoryLLM | None = None,
        completer: TextCompleter | None = None,
        gate: DreamGate | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.root = root or default_memdir()
        self.tools = MemoryTools(self.root)
        self.store = TurnStore(self.root / "turns.sqlite")
        self.llm = client
        self.completer = completer
        self.gate = gate or DreamGate(self.root)
        self._last = self.resident_bundle()
        self._bus = bus
        self._inflight_consolidate: asyncio.Task[None] | None = None
        self._loop_lock = asyncio.Lock()
        self._typed_written: set[str] = set()
        if bus is not None:
            bus.subscribe(RecallRequested, self._on_recall)
            bus.subscribe(TurnClosed, self._on_turn)
            bus.subscribe(CompressionNeeded, self._on_compress)
            bus.subscribe(ClientConnected, self._on_client_connected)
            bus.subscribe(ClientDisconnected, self._on_client_disconnected)

    def last_seen(self):
        return read_last_seen(self.root / ".last_seen")

    def relationship_text(self) -> str:
        return self.tools.read("relationship.md")

    def self_state_text(self) -> str:
        path = self.root / "self_state.md"
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def memory_text(self) -> str:
        return self.tools.read("MEMORY.md")

    def resident_bundle(self) -> PromptContext:
        return PromptContext(index=self.memory_text())

    async def recall(self, ctx: RecallContext, deadline_ms: int) -> PromptContext:
        del ctx, deadline_ms
        self._last = self.resident_bundle()
        return self._last

    def record_turn(self, turn: TurnRecord) -> None:
        if not turn.user_text.strip() and not turn.assistant_text.strip():
            return
        self.store.append(
            turn_id=turn.turn_id,
            user_text=turn.user_text,
            assistant_text=turn.assistant_text,
            interrupted=turn.interrupted,
        )

    async def observe(self, turn: TurnRecord) -> None:
        self.record_turn(turn)

    def _new_turn_count(self) -> int:
        return self.store.count(since=self.gate.last_run(), exclusive=True)

    def _should_consolidate(self) -> bool:
        if self.llm is None:
            return False
        return self._new_turn_count() > 0

    def _consolidate_query(self, started: datetime, new_turns: int) -> str:
        last = self.gate.last_run()
        today = date.today().isoformat()
        since_line = (
            f"用 search_turns(since={last}, order=asc) 读这段新原文。"
            if last
            else "从未巩固过。用 search_turns(order=asc) 从最早一条读。"
        )
        last_label = last or "从未"
        return (
            f"现在：{started.isoformat(timespec='seconds')}\n"
            f"今天日期：{today}\n"
            f"上次跑完：{last_label}\n"
            f"新增轮次：{new_turns}\n"
            f"{since_line}"
            "若 truncated，把 since 推到返回的最后一条 ts 再搜。"
            "按类型写入 user.md / relationship.md / boundaries.md / threads.md。"
            "只有这次改过类型文件，才可以整份重写 MEMORY.md。"
            "不值得则不要写文件。"
        )

    async def consolidate(self) -> None:
        if not self._should_consolidate():
            return
        if self._inflight_consolidate is not None and not self._inflight_consolidate.done():
            return
        self._inflight_consolidate = asyncio.create_task(
            self._consolidate_bg(), name="memory-consolidate"
        )

    async def _consolidate_bg(self) -> None:
        lock = self.gate.try_acquire()
        if not lock:
            return
        started = datetime.now()
        new_turns = self._new_turn_count()
        before = self.memory_text()
        try:
            await self.run(self._consolidate_query(started, new_turns))
            self.gate.mark_run(started)
            self._last = self.resident_bundle()
            if self._bus is not None and self.memory_text() != before:
                await self._bus.publish(ContextReady(context=self._last))
        except Exception:
            logger.exception("consolidate failed")
        finally:
            self.gate.release()

    async def run(
        self,
        query: str,
        *,
        max_steps: int | None = None,
        thinking: bool = True,
    ) -> str:
        if self.llm is None:
            return ""
        async with self._loop_lock:
            return await self._run_locked(query, max_steps=max_steps, thinking=thinking)

    async def _run_locked(
        self,
        query: str,
        *,
        max_steps: int | None,
        thinking: bool,
    ) -> str:
        self._typed_written = set()
        steps = max_steps if max_steps is not None else CONSOLIDATE_STEPS
        schemas = [TOOL_SPECS[name] for name in CONSOLIDATE_TOOLS]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": load_prompt()},
            {"role": "user", "content": query},
        ]
        last = ""
        assert self.llm is not None
        for _ in range(steps):
            turn = await self.llm.complete_with_tools(
                messages,
                schemas,
                thinking=thinking,
                temperature=0.4,
            )
            content = (getattr(turn, "content", None) or "").strip()
            calls = tuple(getattr(turn, "tool_calls", None) or ())
            names = [getattr(call, "name", "") or "" for call in calls]
            logger.info("memory consolidate tools=%s preview=%r", names, content[:120])
            if not calls:
                return content
            last = content
            serialized = []
            for index, call in enumerate(calls):
                name = getattr(call, "name", "") or ""
                arguments = getattr(call, "arguments", None) or "{}"
                call_id = getattr(call, "id", "") or f"call_{index}"
                serialized.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": serialized,
                }
            )
            for spec in serialized:
                result = self._exec(
                    spec["function"]["name"],
                    spec["function"]["arguments"],
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": spec["id"],
                        "content": result,
                    }
                )
        return last

    def _exec(self, name: str, raw_args: str) -> str:
        if name not in CONSOLIDATE_TOOLS:
            return _dump({"error": f"{name} not allowed during consolidate"})
        args = _parse_args(raw_args)
        try:
            if name == "ls":
                return _dump(self.tools.ls(str(args.get("rel", "."))))
            if name == "read":
                return self.tools.read(str(args.get("rel", "")))
            if name == "grep":
                return _dump(
                    self.tools.grep(str(args.get("pattern", ".")), str(args.get("rel", ".")))
                )
            if name == "write":
                rel = normalize_rel(str(args.get("rel", "")))
                blocked = self._memory_blocked(rel)
                if blocked:
                    return blocked
                self.tools.write(rel, str(args.get("content", "")))
                self._note_typed(rel)
                return "ok"
            if name == "write_section":
                rel = normalize_rel(str(args.get("rel", "")))
                blocked = self._memory_blocked(rel)
                if blocked:
                    return blocked
                self.tools.write_section(
                    rel,
                    str(args["heading"]),
                    str(args["body"]),
                )
                self._note_typed(rel)
                return "ok"
            if name == "search_turns":
                n = args.get("n")
                return _dump(
                    self.store.search(
                        pattern=str(args["pattern"]) if args.get("pattern") else None,
                        since=str(args["since"]) if args.get("since") else None,
                        until=str(args["until"]) if args.get("until") else None,
                        day=str(args["day"]) if args.get("day") else None,
                        field=str(args.get("field") or "both"),
                        n=int(n) if n is not None and str(n) != "" else None,
                        order=str(args.get("order") or "desc"),
                    )
                )
        except (KeyError, PermissionError, ValueError) as exc:
            return _dump({"error": f"{type(exc).__name__}: {exc}"})
        return _dump({"error": f"unknown tool {name}"})

    def _memory_blocked(self, rel: str) -> str:
        if rel == "MEMORY.md" and not self._typed_written:
            return _dump(
                {"error": "write MEMORY.md only after a type file this run"}
            )
        return ""

    def _note_typed(self, rel: str) -> None:
        if rel in TYPE_FILES:
            self._typed_written.add(rel)

    async def compress(
        self, messages: list[Message], previous_summary: str = ""
    ) -> str:
        if self.completer is not None:
            try:
                prompt = Path(__file__).parent / "prompts" / "compress.md"
                discarded = "\n".join(f"{item.role}: {item.content}" for item in messages)
                raw = await self.completer.complete(
                    [
                        Message(
                            role="user",
                            content=(
                                f"{prompt.read_text(encoding='utf-8')}\n\n"
                                f"上一份滚动摘要：\n{previous_summary.strip() or '无'}\n\n"
                                f"即将裁掉的原文：\n{discarded or '无'}"
                            ),
                        )
                    ]
                )
                text = clip_summary(raw)
                if text:
                    return text
            except Exception:
                logger.exception("compress llm failed")
        return heuristic_summary(previous_summary, messages)

    async def on_session_start(self) -> PromptContext:
        self._last = self.resident_bundle()
        return self._last

    async def on_session_end(self) -> None:
        seen = self.root / ".last_seen"
        seen.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
        await self.consolidate()

    async def _on_recall(self, event: RecallRequested) -> None:
        del event
        if self._bus is None:
            return
        bundle = await self.recall(RecallContext("", (), ""), 0)
        await self._bus.publish(ContextReady(context=bundle))

    async def _on_turn(self, event: TurnClosed) -> None:
        self.record_turn(
            TurnRecord(
                turn_id=event.turn_id,
                user_text=event.user_text,
                assistant_text=event.assistant_text,
                interrupted=event.interrupted,
            )
        )

    async def _on_compress(self, event: CompressionNeeded) -> None:
        summary = await self.compress(list(event.discarded), event.previous_summary)
        try:
            rolling = self.root / "rolling.md"
            rolling.write_text(summary.rstrip() + ("\n" if summary.strip() else ""), encoding="utf-8")
        except Exception:
            logger.exception("failed to write rolling.md")
        if self._bus is None:
            return
        await self._bus.publish(SummaryReady(text=summary, drop_prefix=0))

    async def _on_client_connected(self, event: ClientConnected) -> None:
        del event
        if self._bus is None:
            return
        bundle = await self.on_session_start()
        await self._bus.publish(ContextReady(context=bundle))
        rolling_path = self.root / "rolling.md"
        rolling = ""
        if rolling_path.is_file():
            rolling = rolling_path.read_text(encoding="utf-8").strip()
        if rolling:
            await self._bus.publish(SummaryReady(text=rolling, drop_prefix=0))

    async def _on_client_disconnected(self, event: ClientDisconnected) -> None:
        del event
        await self.on_session_end()

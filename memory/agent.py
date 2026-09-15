from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime
from pathlib import Path

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

from .dream import DreamGate
from .paths import default_memdir, read_last_seen
from .tools import MemoryTools
from .types import RecallContext, TurnRecord

TOOL_SCHEMA = [
    {"name": "ls", "description": "List files under memdir", "parameters": {"rel": "."}},
    {"name": "read", "description": "Read a memory file", "parameters": {"rel": ""}},
    {"name": "grep", "description": "Search memory files", "parameters": {"pattern": "", "rel": "."}},
    {"name": "write_section", "description": "Replace a markdown section", "parameters": {"rel": "", "heading": "", "body": ""}},
    {"name": "append", "description": "Append to a daily log", "parameters": {"rel": "", "text": ""}},
]


class MemoryAgent:
    def __init__(
        self,
        root: Path | None = None,
        client=None,
        dream: DreamGate | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.root = root or default_memdir()
        self.tools = MemoryTools(self.root)
        self.client = client
        self.dream = dream or DreamGate(self.root)
        self._last = PromptContext()
        self._bus = bus
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
        return self.tools.read("self_state.md")

    def resident_bundle(self, snippets: tuple[str, ...] = ()) -> PromptContext:
        return PromptContext(
            index=self.tools.read("MEMORY.md"),
            relationship=self.tools.read("relationship.md"),
            self_state=self.tools.read("self_state.md"),
            snippets=snippets,
            open_threads=(),
        )

    async def recall(self, ctx: RecallContext, deadline_ms: int) -> PromptContext:
        try:
            bundle = await asyncio.wait_for(self._recall(ctx), timeout=max(deadline_ms / 1000, 0.05))
            self._last = bundle
            return bundle
        except (TimeoutError, asyncio.TimeoutError):
            return self._last or self.resident_bundle()

    async def _recall(self, ctx: RecallContext) -> PromptContext:
        if self.client is not None:
            result = await self._tool_loop("recall", ctx.text, max_steps=3)
            snippets = tuple(result.get("snippets", [])) if isinstance(result, dict) else ()
            return self.resident_bundle(snippets)
        query = re.escape(ctx.text[:12]) if ctx.text.strip() else "."
        hits = self.tools.grep(query, ".") if ctx.text else []
        snippets = tuple(hits[:5])
        return self.resident_bundle(snippets)

    async def observe(self, turn: TurnRecord) -> None:
        today = f"logs/{date.today().isoformat()}.md"
        if self.client is not None:
            await self._tool_loop("extract", f"{turn.user_text}\n{turn.assistant_text}", max_steps=4)
            return
        if turn.user_text.strip():
            self.tools.append(today, f"- {turn.user_text} → {turn.assistant_text[:80]}")

    async def compress(self, messages: list[Message]) -> str:
        if self.client is not None:
            result = await self._tool_loop(
                "compress",
                "\n".join(f"{m.role}: {m.content}" for m in messages[:40]),
                max_steps=2,
            )
            if isinstance(result, dict):
                return str(result.get("summary", ""))
        return "；".join(m.content[:40] for m in messages[:8] if m.role == "user")

    async def on_session_start(self) -> PromptContext:
        self._last = self.resident_bundle()
        return self._last

    async def on_session_end(self) -> None:
        self.dream.note_session()
        if self.dream.should_run():
            lock = self.dream.try_acquire()
            if lock:
                try:
                    if self.client is not None:
                        await self._tool_loop("dream", "consolidate", max_steps=20, thinking=True)
                    else:
                        self._heuristic_dream()
                    self.dream.mark_success()
                finally:
                    self.dream.release()
        seen = self.root / ".last_seen"
        seen.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")

    async def _tool_loop(self, kind: str, query: str, max_steps: int, thinking: bool = False) -> dict:
        del thinking
        if self.client is None:
            return {}
        messages = [{"role": "user", "content": f"{kind}\n{query}"}]
        for _ in range(max_steps):
            response = await self.client(messages, TOOL_SCHEMA)
            if not isinstance(response, dict):
                continue
            if response.get("type") == "result":
                return response.get("data") or {}
            name = response.get("name")
            args = response.get("arguments") or {}
            result = self._exec(name, args)
            messages.append({"role": "tool", "content": json.dumps(result, ensure_ascii=False)})
        return {}

    def _exec(self, name: str | None, args: dict) -> object:
        if name == "ls":
            return self.tools.ls(str(args.get("rel", ".")))
        if name == "read":
            return self.tools.read(str(args.get("rel", "")))
        if name == "grep":
            return self.tools.grep(str(args.get("pattern", ".")), str(args.get("rel", ".")))
        if name == "write_section":
            self.tools.write_section(str(args["rel"]), str(args["heading"]), str(args["body"]))
            return "ok"
        if name == "append":
            self.tools.append(str(args["rel"]), str(args["text"]))
            return "ok"
        return {"error": f"unknown tool {name}"}

    def _heuristic_dream(self) -> None:
        for rel in ("relationship.md", "self_state.md"):
            text = self.tools.read(rel)
            if not text.strip():
                continue
            seen: set[str] = set()
            out: list[str] = []
            changed = False
            for line in text.splitlines():
                key = line.strip()
                if key.startswith("- "):
                    if key in seen:
                        changed = True
                        continue
                    seen.add(key)
                out.append(line)
            if not changed:
                continue
            (self.root / rel).write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
            self.tools._log(rel, "dream", "dedupe")

    async def _on_recall(self, event: RecallRequested) -> None:
        asyncio.create_task(self._recall_and_publish(event))

    async def _recall_and_publish(self, event: RecallRequested) -> None:
        if self._bus is None:
            return
        bundle = await self.recall(
            RecallContext(text=event.text, recent=event.recent, now_iso=""),
            event.deadline_ms,
        )
        await self._bus.publish(ContextReady(context=bundle))

    async def _on_turn(self, event: TurnClosed) -> None:
        asyncio.create_task(
            self.observe(
                TurnRecord(
                    turn_id=event.turn_id,
                    user_text=event.user_text,
                    assistant_text=event.assistant_text,
                    interrupted=event.interrupted,
                )
            )
        )

    async def _on_compress(self, event: CompressionNeeded) -> None:
        if self._bus is None:
            return
        summary = await self.compress(list(event.messages))
        await self._bus.publish(SummaryReady(text=summary))

    async def _on_client_connected(self, event: ClientConnected) -> None:
        del event
        if self._bus is None:
            return
        bundle = await self.on_session_start()
        await self._bus.publish(ContextReady(context=bundle))

    async def _on_client_disconnected(self, event: ClientDisconnected) -> None:
        del event
        await self.on_session_end()

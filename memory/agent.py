from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime
from pathlib import Path

from typing import Protocol

from asm.brain.compact import clip_summary, heuristic_summary
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
from .supervisor import MemoryLLM, MemorySupervisor
from .tools import MemoryTools
from .types import RecallContext, TurnRecord
from .worth import skip_extract, skip_recall

logger = logging.getLogger(__name__)


class TextCompleter(Protocol):
    async def complete(self, messages: list[Message]) -> str: ...


class MemoryAgent:
    def __init__(
        self,
        root: Path | None = None,
        client: MemoryLLM | None = None,
        completer: TextCompleter | None = None,
        dream: DreamGate | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.root = root or default_memdir()
        self.tools = MemoryTools(self.root)
        self.completer = completer
        self.supervisor = MemorySupervisor(self.tools, client)
        self.dream = dream or DreamGate(self.root)
        self._last = self.resident_bundle()
        self._bus = bus
        self._visit_id = 0
        self._visit_started = datetime.now()
        self._extracted_visit = -1
        self._last_recall_text = ""
        self._queued_recall: RecallRequested | None = None
        self._recall_drain: asyncio.Task[None] | None = None
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

    def memory_text(self) -> str:
        return self.tools.read("MEMORY.md")

    def resident_bundle(self) -> PromptContext:
        return PromptContext(index=self.memory_text())

    async def recall(self, ctx: RecallContext, deadline_ms: int) -> PromptContext:
        text = ctx.text.strip()
        if skip_recall(text, self._last_recall_text):
            return self._last
        self._last_recall_text = text
        try:
            bundle = await asyncio.wait_for(
                self._recall(ctx),
                timeout=max(deadline_ms / 1000, 0.05),
            )
            self._last = bundle
            return bundle
        except (TimeoutError, asyncio.TimeoutError):
            return self._last

    async def _recall(self, ctx: RecallContext) -> PromptContext:
        if self.supervisor.llm is None:
            return self.resident_bundle()
        now = datetime.now().isoformat(timespec="minutes")
        recent = "\n".join(f"{item.role}: {item.content}" for item in ctx.recent[-8:]) or "（无）"
        await self.supervisor.run(
            "recall",
            (
                f"现在：{now}\n"
                f"当前 MEMORY.md：\n{self.memory_text().strip() or '（空）'}\n\n"
                f"他刚说/正在说：{ctx.text}\n"
                f"近期对话：\n{recent}\n\n"
                "把这轮她开口还用得着、工作集里还没有的档案内容晋升进 MEMORY.md。"
                "过时的撤下。"
            ),
        )
        return self.resident_bundle()

    def record_turn(self, turn: TurnRecord) -> None:
        if not turn.user_text.strip() and not turn.assistant_text.strip():
            return
        path = self.root / "transcripts" / f"{date.today().isoformat()}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "turn_id": turn.turn_id,
            "user": turn.user_text,
            "assistant": turn.assistant_text,
            "interrupted": turn.interrupted,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    async def observe(self, turn: TurnRecord) -> None:
        self.record_turn(turn)

    async def extract_visit(self) -> None:
        if self._extracted_visit == self._visit_id:
            return
        self._extracted_visit = self._visit_id
        rows = self._transcripts_since(self._visit_started)
        if skip_extract(rows):
            return
        if self.supervisor.llm is None:
            return
        today = date.today().isoformat()
        body = "\n".join(
            f"{row.get('ts', '')} user={row.get('user', '')} assistant={row.get('assistant', '')}"
            for row in rows
        )
        await self.supervisor.run(
            "extract",
            (
                f"今天日期：{today}\n"
                f"本段 transcript（离开前）：\n{body}\n\n"
                f"若值得记，append 到 logs/{today}.md。不值得则不要调用工具。"
            ),
        )

    def _transcripts_since(self, started: datetime) -> list[dict]:
        folder = self.root / "transcripts"
        if not folder.is_dir():
            return []
        rows: list[dict] = []
        for path in sorted(folder.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                raw_ts = item.get("ts") or ""
                try:
                    ts = datetime.fromisoformat(str(raw_ts))
                except ValueError:
                    rows.append(item)
                    continue
                if ts >= started.replace(microsecond=0):
                    rows.append(item)
        return rows

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
        self._visit_id += 1
        self._visit_started = datetime.now()
        self._last_recall_text = ""
        self._last = self.resident_bundle()
        return self._last

    async def on_session_end(self) -> None:
        self.dream.note_session()
        seen = self.root / ".last_seen"
        seen.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
        if not self.dream.should_run():
            return
        asyncio.create_task(self._dream_bg())

    async def _dream_bg(self) -> None:
        lock = self.dream.try_acquire()
        if not lock:
            return
        try:
            if self.supervisor.llm is not None:
                now = datetime.now().isoformat(timespec="minutes")
                await self.supervisor.run(
                    "dream",
                    f"现在：{now}\n巩固档案。persona.md 只读。MEMORY.md 工作集硬帽 200 行 / 25KB。",
                )
            else:
                self._heuristic_dream()
            self.dream.mark_success()
        except Exception:
            logger.exception("dream failed")
        finally:
            self.dream.release()

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
        self._queued_recall = event
        if self._recall_drain is None or self._recall_drain.done():
            self._recall_drain = asyncio.create_task(self._drain_recall())

    async def _drain_recall(self) -> None:
        while self._queued_recall is not None:
            event = self._queued_recall
            self._queued_recall = None
            await self._recall_and_publish(event)

    async def _recall_and_publish(self, event: RecallRequested) -> None:
        if self._bus is None:
            return
        if skip_recall(event.text, self._last_recall_text):
            return
        bundle = await self.recall(
            RecallContext(text=event.text, recent=event.recent, now_iso=""),
            event.deadline_ms,
        )
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
        rolling = self.tools.read("rolling.md").strip()
        if rolling:
            await self._bus.publish(SummaryReady(text=rolling, drop_prefix=0))

    async def _on_client_disconnected(self, event: ClientDisconnected) -> None:
        del event
        try:
            await self.extract_visit()
        except Exception:
            logger.exception("extract failed")
        await self.on_session_end()

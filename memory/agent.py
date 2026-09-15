from __future__ import annotations

import asyncio
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
from .supervisor import CONSOLIDATE, MemoryLLM, MemorySupervisor
from .tools import MemoryTools
from .turns import TurnStore
from .types import RecallContext, TurnRecord

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
        self.store = TurnStore(self.root / "turns.sqlite")
        self.completer = completer
        self.supervisor = MemorySupervisor(self.tools, client, turns=self.store)
        self.dream = dream or DreamGate(self.root)
        self._last = self.resident_bundle()
        self._bus = bus
        self._inflight_consolidate: asyncio.Task[None] | None = None
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
        return self.store.count(since=self.dream.last_run(), exclusive=True)

    def _should_consolidate(self) -> bool:
        if self.supervisor.llm is None:
            return False
        return self._new_turn_count() > 0

    def _consolidate_query(self, started: datetime, new_turns: int) -> str:
        last = self.dream.last_run()
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
        lock = self.dream.try_acquire()
        if not lock:
            return
        started = datetime.now()
        new_turns = self._new_turn_count()
        before = self.memory_text()
        try:
            await self.supervisor.run(
                CONSOLIDATE,
                self._consolidate_query(started, new_turns),
            )
            self.dream.mark_run(started)
            self._last = self.resident_bundle()
            if self._bus is not None and self.memory_text() != before:
                await self._bus.publish(ContextReady(context=self._last))
        except Exception:
            logger.exception("consolidate failed")
        finally:
            self.dream.release()

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

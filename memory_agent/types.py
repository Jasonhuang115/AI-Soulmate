from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from asm.core.interfaces import Message


@dataclass(frozen=True, slots=True)
class RecallContext:
    text: str
    recent: tuple[Message, ...]
    now_iso: str


@dataclass(frozen=True, slots=True)
class TurnRecord:
    turn_id: str
    user_text: str
    assistant_text: str
    interrupted: bool


@dataclass(frozen=True, slots=True)
class ToolCallDelta:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class CompletionMessage:
    content: str = ""
    tool_calls: tuple[ToolCallDelta, ...] = ()


class MemoryLLM(Protocol):
    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        thinking: bool = False,
        temperature: float = 0.3,
    ) -> CompletionMessage: ...

from __future__ import annotations

from dataclasses import dataclass

from asm.core.interfaces import Message, PromptContext

MemoryBundle = PromptContext


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

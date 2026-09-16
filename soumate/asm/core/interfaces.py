from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


class TimerHandle(Protocol):
    def cancel(self) -> None: ...


class Clock(Protocol):
    def now(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...

    def call_later(self, seconds: float, cb: Callable[[], Any]) -> TimerHandle: ...


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class PromptContext:
    index: str = ""


@dataclass(frozen=True, slots=True)
class TurnRequest:
    turn_id: str
    text: str
    speculative: bool
    context: PromptContext
    messages: tuple[Message, ...]
    session_summary: str


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


class SpeechPerceiver(Protocol):
    async def feed(self, pcm16: bytes) -> None: ...

    async def close(self) -> None: ...


class Brain(Protocol):
    async def start_turn(self, req: TurnRequest) -> None: ...

    async def cancel(self, turn_id: str) -> None: ...


class TTSEngine(Protocol):
    def synthesize(
        self, turn_id: str, sentence_idx: int, text: str
    ) -> AsyncIterator[Any]: ...

    async def cancel(self, turn_id: str) -> None: ...


class ToolProvider(Protocol):
    def tools(self) -> list[ToolSpec]: ...

    async def handle(self, call: Any) -> None: ...

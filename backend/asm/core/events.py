from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from asm.core.interfaces import Message, PromptContext


class DialogState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    SPECULATING = "speculating"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass(frozen=True, slots=True)
class Cancel:
    turn_id: str


@dataclass(frozen=True, slots=True)
class StartTurn:
    turn_id: str
    text: str
    speculative: bool
    context: PromptContext


@dataclass(frozen=True, slots=True)
class Commit:
    turn_id: str


@dataclass(frozen=True, slots=True)
class TurnDone:
    turn_id: str


@dataclass(frozen=True, slots=True)
class TurnAborted:
    turn_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class SpeechStarted:
    pass


@dataclass(frozen=True, slots=True)
class SpeechEnded:
    pass


@dataclass(frozen=True, slots=True)
class PartialTranscript:
    text: str


@dataclass(frozen=True, slots=True)
class UtteranceEnd:
    text: str


@dataclass(frozen=True, slots=True)
class TextDelta:
    turn_id: str
    text: str


@dataclass(frozen=True, slots=True)
class SentenceEnd:
    turn_id: str
    sentence_idx: int
    text: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    turn_id: str
    sentence_idx: int
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CompressionNeeded:
    messages: tuple[Message, ...]


@dataclass(frozen=True, slots=True)
class AudioChunk:
    turn_id: str
    sentence_idx: int
    seq: int
    pcm16: bytes
    sample_rate: int
    mouth_energy: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class VoiceError:
    turn_id: str
    message: str


@dataclass(frozen=True, slots=True)
class TextInput:
    text: str


@dataclass(frozen=True, slots=True)
class SpokenProgress:
    turn_id: str
    sentence_idx: int


@dataclass(frozen=True, slots=True)
class MicState:
    open: bool


@dataclass(frozen=True, slots=True)
class StateChanged:
    state: DialogState


@dataclass(frozen=True, slots=True)
class Duck:
    pass


@dataclass(frozen=True, slots=True)
class Unduck:
    pass


@dataclass(frozen=True, slots=True)
class ProactiveTrigger:
    reason: str
    hint: str


@dataclass(frozen=True, slots=True)
class AvatarCommand:
    turn_id: str | None
    sentence_idx: int | None
    expression: str | None
    motion: str | None
    immediate: bool = False


@dataclass(frozen=True, slots=True)
class LatencyMark:
    turn_id: str
    marks: dict[str, float]


@dataclass(frozen=True, slots=True)
class RecallRequested:
    text: str
    recent: tuple[Message, ...]
    deadline_ms: int = 400


@dataclass(frozen=True, slots=True)
class ContextReady:
    context: PromptContext


@dataclass(frozen=True, slots=True)
class TurnClosed:
    turn_id: str
    user_text: str
    assistant_text: str
    interrupted: bool


@dataclass(frozen=True, slots=True)
class SummaryReady:
    text: str


@dataclass(frozen=True, slots=True)
class ClientConnected:
    pass


@dataclass(frozen=True, slots=True)
class ClientDisconnected:
    pass

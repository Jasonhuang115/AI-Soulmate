from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from asm.core.events import DialogState
from asm.core.interfaces import Message, PromptContext


@dataclass
class Session:
    current_turn_id: str | None = None
    state: DialogState = DialogState.IDLE
    messages: list[Message] = field(default_factory=list)
    spoken_upto: dict[str, int] = field(default_factory=dict)
    last_context: PromptContext = field(default_factory=PromptContext)
    session_summary: str = ""
    last_user_text: str = ""
    pending_sentences: dict[str, list[str]] = field(default_factory=dict)
    last_chat_at: float | None = None

    def begin_turn(self) -> str:
        turn_id = str(uuid.uuid4())
        self.current_turn_id = turn_id
        self.pending_sentences[turn_id] = []
        self.spoken_upto[turn_id] = -1
        return turn_id

    def append_user(self, text: str) -> None:
        self.last_user_text = text
        self.messages.append(Message(role="user", content=text))

    def record_sentence(self, turn_id: str, sentence_idx: int, text: str) -> None:
        pending = self.pending_sentences.setdefault(turn_id, [])
        while len(pending) <= sentence_idx:
            pending.append("")
        pending[sentence_idx] = text

    def append_assistant_spoken(self, turn_id: str, sentence_idx: int) -> None:
        self.spoken_upto[turn_id] = sentence_idx

    def mark_interrupted(self, turn_id: str | None = None) -> None:
        tid = turn_id or self.current_turn_id
        if tid is None:
            return
        spoken_idx = self.spoken_upto.get(tid, -1)
        pending = self.pending_sentences.get(tid, [])
        spoken = [s for s in pending[: spoken_idx + 1] if s]
        content = "".join(spoken)
        if content:
            self.messages.append(Message(role="assistant", content=f"{content} [被打断]"))
        else:
            self.messages.append(Message(role="assistant", content="[被打断]"))

    def finalize_assistant(self, turn_id: str) -> None:
        pending = self.pending_sentences.get(turn_id, [])
        spoken_idx = self.spoken_upto.get(turn_id, -1)
        if spoken_idx < 0:
            spoken = [s for s in pending if s]
        else:
            spoken = [s for s in pending[: spoken_idx + 1] if s]
            if not spoken:
                spoken = [s for s in pending if s]
        text = "".join(spoken)
        if text:
            self.messages.append(Message(role="assistant", content=text))

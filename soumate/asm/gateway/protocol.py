from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from asm.core.events import (
    AudioChunk,
    AvatarCommand,
    Cancel,
    Commit,
    Duck,
    LatencyMark,
    MicState,
    PartialTranscript,
    PlaybackDone,
    SentenceEnd,
    SpokenProgress,
    StateChanged,
    TextDelta,
    TextInput,
    TurnDone,
    Unduck,
    UtteranceEnd,
    VoiceError,
)


class InboundMessage(BaseModel):
    type: str
    text: str | None = None
    turn_id: str | None = None
    sentence_idx: int | None = None
    open: bool | None = None


def parse_inbound(raw: str) -> TextInput | SpokenProgress | MicState | PlaybackDone | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        msg = InboundMessage.model_validate(data)
    except ValidationError:
        return None
    if msg.type == "text_input" and isinstance(msg.text, str):
        return TextInput(text=msg.text)
    if msg.type == "spoken_progress" and msg.turn_id is not None and msg.sentence_idx is not None:
        return SpokenProgress(turn_id=msg.turn_id, sentence_idx=msg.sentence_idx)
    if msg.type == "playback_done" and msg.turn_id is not None:
        return PlaybackDone(turn_id=msg.turn_id)
    if msg.type == "mic_state" and msg.open is not None:
        return MicState(open=msg.open)
    return None


def encode_outbound(event: object) -> str | None:
    payload: dict[str, Any] | None = None
    if isinstance(event, TextDelta):
        payload = {"type": "text_delta", "turn_id": event.turn_id, "text": event.text}
    elif isinstance(event, StateChanged):
        payload = {"type": "state", "state": event.state.value}
    elif isinstance(event, Cancel):
        payload = {"type": "cancel", "turn_id": event.turn_id}
    elif isinstance(event, TurnDone):
        payload = {"type": "turn_done", "turn_id": event.turn_id}
    elif isinstance(event, Commit):
        payload = {"type": "commit", "turn_id": event.turn_id}
    elif isinstance(event, SentenceEnd):
        payload = {
            "type": "sentence",
            "turn_id": event.turn_id,
            "sentence_idx": event.sentence_idx,
            "text": event.text,
        }
    elif isinstance(event, AudioChunk):
        import base64

        payload = {
            "type": "audio_chunk",
            "turn_id": event.turn_id,
            "sentence_idx": event.sentence_idx,
            "seq": event.seq,
            "sample_rate": event.sample_rate,
            "mouth_energy": list(event.mouth_energy),
            "pcm_b64": base64.b64encode(event.pcm16).decode("ascii"),
        }
    elif isinstance(event, Duck):
        payload = {"type": "duck"}
    elif isinstance(event, Unduck):
        payload = {"type": "unduck"}
    elif isinstance(event, AvatarCommand):
        payload = {
            "type": "avatar_command",
            "turn_id": event.turn_id,
            "sentence_idx": event.sentence_idx,
            "expression": event.expression,
            "motion": event.motion,
            "motions": list(event.motions),
            "control": event.control,
            "intensity": event.intensity,
            "immediate": event.immediate,
        }
    elif isinstance(event, LatencyMark):
        payload = {"type": "latency", "turn_id": event.turn_id, "marks": event.marks}
    elif isinstance(event, VoiceError):
        payload = {"type": "error", "message": event.message}
    elif isinstance(event, PartialTranscript):
        payload = {"type": "partial_transcript", "text": event.text}
    elif isinstance(event, UtteranceEnd):
        payload = {"type": "utterance_end", "text": event.text}
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False)

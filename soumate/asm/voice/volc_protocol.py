from __future__ import annotations

import json
from dataclasses import dataclass, field

PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001
FULL_CLIENT_REQUEST = 0b0001
AUDIO_ONLY_RESPONSE = 0b1011
FULL_SERVER_RESPONSE = 0b1001
ERROR_INFORMATION = 0b1111
FLAG_WITH_EVENT = 0b0100
JSON = 0b0001
NO_SERIALIZATION = 0b0000
COMPRESSION_NO = 0b0000

EVENT_START_CONNECTION = 1
EVENT_FINISH_CONNECTION = 2
EVENT_CONNECTION_STARTED = 50
EVENT_CONNECTION_FAILED = 51
EVENT_START_SESSION = 100
EVENT_FINISH_SESSION = 102
EVENT_SESSION_STARTED = 150
EVENT_SESSION_FINISHED = 152
EVENT_SESSION_FAILED = 153
EVENT_TASK_REQUEST = 200
EVENT_TTS_RESPONSE = 352


def _header(message_type: int, flags: int, serial: int) -> bytes:
    return bytes(
        [
            (PROTOCOL_VERSION << 4) | DEFAULT_HEADER_SIZE,
            (message_type << 4) | flags,
            (serial << 4) | COMPRESSION_NO,
            0,
        ]
    )


def _optional(event: int, session_id: str | None) -> bytes:
    raw = bytearray(event.to_bytes(4, "big", signed=True))
    if session_id is not None:
        sid = session_id.encode("utf-8")
        raw.extend(len(sid).to_bytes(4, "big", signed=True))
        raw.extend(sid)
    return bytes(raw)


def encode_event(event: int, session_id: str | None = None, payload: dict | None = None) -> bytes:
    serial = JSON if payload is not None else NO_SERIALIZATION
    frame = bytearray(_header(FULL_CLIENT_REQUEST, FLAG_WITH_EVENT, serial))
    frame.extend(_optional(event, session_id))
    body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    frame.extend(len(body).to_bytes(4, "big", signed=True))
    frame.extend(body)
    return bytes(frame)


def session_payload(text: str, speaker: str, event: int) -> dict:
    return {
        "user": {"uid": "asm"},
        "event": event,
        "namespace": "BidirectionalTTS",
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {"format": "pcm", "sample_rate": 24000},
        },
    }


@dataclass
class ParsedFrame:
    message_type: int
    event: int = 0
    session_id: str = ""
    payload: bytes = b""
    payload_json: str = ""
    extras: dict = field(default_factory=dict)


def _read_len_str(buf: bytes, offset: int) -> tuple[str, int]:
    size = int.from_bytes(buf[offset : offset + 4], "big")
    offset += 4
    text = buf[offset : offset + size].decode("utf-8")
    return text, offset + size


def _read_len_bytes(buf: bytes, offset: int) -> tuple[bytes, int]:
    size = int.from_bytes(buf[offset : offset + 4], "big")
    offset += 4
    return buf[offset : offset + size], offset + size


def parse_frame(buf: bytes) -> ParsedFrame:
    if len(buf) < 4:
        raise ValueError("short frame")
    message_type = (buf[1] >> 4) & 0x0F
    flags = buf[1] & 0x0F
    serial = (buf[2] >> 4) & 0x0F
    offset = 4
    frame = ParsedFrame(message_type=message_type)
    if flags & FLAG_WITH_EVENT and offset + 4 <= len(buf):
        frame.event = int.from_bytes(buf[offset : offset + 4], "big", signed=True)
        offset += 4
        if frame.event == EVENT_CONNECTION_STARTED and offset + 4 <= len(buf):
            frame.extras["connection_id"], offset = _read_len_str(buf, offset)
        elif frame.event == EVENT_CONNECTION_FAILED and offset + 4 <= len(buf):
            frame.payload_json, offset = _read_len_str(buf, offset)
        elif frame.event not in (EVENT_START_CONNECTION, EVENT_FINISH_CONNECTION) and offset + 4 <= len(buf):
            frame.session_id, offset = _read_len_str(buf, offset)
    if offset + 4 <= len(buf) and not frame.payload and not frame.payload_json:
        payload, _offset = _read_len_bytes(buf, offset)
        if serial == JSON:
            frame.payload_json = payload.decode("utf-8", errors="replace")
        else:
            frame.payload = payload
    return frame

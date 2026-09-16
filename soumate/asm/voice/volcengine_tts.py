from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

import websockets

from asm.core.config import Settings
from asm.core.events import AudioChunk
from asm.voice.mouth_energy import mouth_energy
from asm.voice.volc_protocol import (
    EVENT_CONNECTION_STARTED,
    EVENT_FINISH_SESSION,
    EVENT_SESSION_FAILED,
    EVENT_SESSION_FINISHED,
    EVENT_SESSION_STARTED,
    EVENT_START_CONNECTION,
    EVENT_START_SESSION,
    EVENT_TASK_REQUEST,
    EVENT_TTS_RESPONSE,
    encode_event,
    parse_frame,
    session_payload,
)

logger = logging.getLogger(__name__)
TTS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"


class VolcengineTTS:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ws = None
        self._lock = asyncio.Lock()
        self._cancelled: set[str] = set()

    async def cancel(self, turn_id: str) -> None:
        self._cancelled.add(turn_id)

    async def synthesize(
        self, turn_id: str, sentence_idx: int, text: str
    ) -> AsyncIterator[AudioChunk]:
        if turn_id in self._cancelled:
            return
        async with self._lock:
            yielded = False
            for attempt in range(2):
                try:
                    async for chunk in self._session(turn_id, sentence_idx, text):
                        yielded = True
                        yield chunk
                    return
                except websockets.exceptions.ConnectionClosed:
                    self._forget_ws()
                    if yielded or attempt == 1:
                        raise
                    logger.warning("tts websocket closed; reconnecting")

    async def _session(
        self, turn_id: str, sentence_idx: int, text: str
    ) -> AsyncIterator[AudioChunk]:
        ws = await self._ensure_ws()
        session_id = uuid.uuid4().hex
        await ws.send(
            encode_event(
                EVENT_START_SESSION,
                session_id,
                session_payload("", self._settings.volc_tts_speaker, EVENT_START_SESSION),
            )
        )
        started = parse_frame(await ws.recv())
        if started.event != EVENT_SESSION_STARTED:
            self._forget_ws()
            raise RuntimeError(f"tts session failed to start: {started}")
        await ws.send(
            encode_event(
                EVENT_TASK_REQUEST,
                session_id,
                session_payload(text, self._settings.volc_tts_speaker, EVENT_TASK_REQUEST),
            )
        )
        await ws.send(encode_event(EVENT_FINISH_SESSION, session_id, {}))
        seq = 0
        while True:
            if turn_id in self._cancelled:
                return
            raw = await ws.recv()
            if isinstance(raw, str):
                raise RuntimeError(raw)
            frame = parse_frame(raw)
            if frame.event == EVENT_TTS_RESPONSE and frame.payload:
                energy = tuple(mouth_energy(frame.payload, 24000))
                yield AudioChunk(
                    turn_id=turn_id,
                    sentence_idx=sentence_idx,
                    seq=seq,
                    pcm16=frame.payload,
                    sample_rate=24000,
                    mouth_energy=energy,
                )
                seq += 1
            if frame.event in (EVENT_SESSION_FINISHED, EVENT_SESSION_FAILED):
                if frame.event == EVENT_SESSION_FAILED:
                    raise RuntimeError(frame.payload_json or "tts session failed")
                return

    def _is_open(self) -> bool:
        ws = self._ws
        if ws is None:
            return False
        state = getattr(ws, "state", None)
        return getattr(state, "name", "") == "OPEN"

    def _forget_ws(self) -> None:
        self._ws = None

    async def _ensure_ws(self):
        if self._is_open():
            return self._ws
        self._ws = None
        headers = {
            "X-Api-Resource-Id": self._settings.volc_tts_resource_id,
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
        if self._settings.volc_tts_api_key:
            headers["X-Api-Key"] = self._settings.volc_tts_api_key
        else:
            headers["X-Api-App-Key"] = self._settings.volc_tts_app_key
            headers["X-Api-Access-Key"] = self._settings.volc_tts_access_key
        self._ws = await websockets.connect(TTS_URL, additional_headers=headers)
        await self._ws.send(encode_event(EVENT_START_CONNECTION, payload={}))
        raw = await self._ws.recv()
        if isinstance(raw, str):
            raise RuntimeError(raw)
        frame = parse_frame(raw)
        if frame.event != EVENT_CONNECTION_STARTED:
            raise RuntimeError(f"tts connection failed: {frame}")
        return self._ws

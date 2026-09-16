from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect

from asm.core.bus import EventBus
from asm.core.events import (
    AudioChunk,
    AvatarCommand,
    Cancel,
    ClientConnected,
    ClientDisconnected,
    Commit,
    Duck,
    LatencyMark,
    PartialTranscript,
    SentenceEnd,
    StateChanged,
    TextDelta,
    TurnDone,
    Unduck,
    UtteranceEnd,
    VoiceError,
)
from asm.core.interfaces import SpeechPerceiver
from asm.gateway.protocol import encode_outbound, parse_inbound

logger = logging.getLogger(__name__)

_FORWARD_TYPES = (
    TextDelta,
    StateChanged,
    Cancel,
    TurnDone,
    Commit,
    SentenceEnd,
    AudioChunk,
    Duck,
    Unduck,
    AvatarCommand,
    LatencyMark,
    VoiceError,
    PartialTranscript,
    UtteranceEnd,
)


async def handle_socket(
    websocket: WebSocket,
    bus: EventBus,
    perceiver: SpeechPerceiver | None = None,
) -> None:
    await websocket.accept()
    await bus.publish(ClientConnected())
    queue: asyncio.Queue[object] = asyncio.Queue()
    closed = False

    async def forward(event: object) -> None:
        if closed:
            return
        await queue.put(event)

    for event_type in _FORWARD_TYPES:
        bus.subscribe(event_type, forward)

    async def reader() -> None:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect
            data = message.get("bytes")
            if data:
                if perceiver is not None:
                    await perceiver.feed(data)
                continue
            raw = message.get("text")
            if not raw:
                continue
            inbound = parse_inbound(raw)
            if inbound is None:
                logger.warning("drop inbound: %s", raw[:200])
                continue
            await bus.publish(inbound)

    async def writer() -> None:
        while True:
            event = await queue.get()
            payload = encode_outbound(event)
            if payload is None:
                continue
            await websocket.send_text(payload)

    try:
        await asyncio.gather(reader(), writer())
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("websocket closed with error")
    finally:
        closed = True
        for event_type in _FORWARD_TYPES:
            bus.unsubscribe(event_type, forward)
        await bus.publish(ClientDisconnected())
        if perceiver is not None:
            await perceiver.close()

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
Handler = Callable[[T], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Any], list[Handler[Any]]] = defaultdict(list)

    def subscribe(self, event_type: type[T], handler: Handler[T]) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[T], handler: Handler[T]) -> None:
        handlers = self._handlers.get(event_type)
        if not handlers:
            return
        self._handlers[event_type] = [h for h in handlers if h is not handler]

    async def publish(self, event: object) -> None:
        for event_type, handlers in list(self._handlers.items()):
            if not isinstance(event, event_type):
                continue
            for handler in handlers:
                try:
                    await handler(event)
                except Exception:
                    logger.exception("handler failed for %s", type(event).__name__)

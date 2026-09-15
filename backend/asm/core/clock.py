from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class SystemClock:
    def now(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def call_later(self, seconds: float, cb: Callable[[], Any]) -> asyncio.TimerHandle:
        loop = asyncio.get_running_loop()

        def wrapper() -> None:
            result = cb()
            if inspect.isawaitable(result):
                loop.create_task(result)

        return loop.call_later(seconds, wrapper)


@dataclass
class FakeTimerHandle:
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


@dataclass
class FakeClock:
    _now: float = 0.0
    _sleeps: list[tuple[float, asyncio.Future[None]]] = field(default_factory=list)
    _later: list[tuple[float, Callable[[], Any], FakeTimerHandle]] = field(
        default_factory=list
    )

    def now(self) -> float:
        return self._now

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        self._sleeps.append((self._now + seconds, fut))
        await fut

    def call_later(self, seconds: float, cb: Callable[[], Any]) -> FakeTimerHandle:
        handle = FakeTimerHandle()
        self._later.append((self._now + seconds, cb, handle))
        return handle

    async def advance(self, seconds: float) -> None:
        target = self._now + seconds
        while True:
            next_wake: float | None = None
            for wake_at, fut in self._sleeps:
                if not fut.done() and wake_at <= target:
                    if next_wake is None or wake_at < next_wake:
                        next_wake = wake_at
            for wake_at, _cb, handle in self._later:
                if not handle.cancelled and wake_at <= target:
                    if next_wake is None or wake_at < next_wake:
                        next_wake = wake_at
            if next_wake is None:
                self._now = target
                return
            self._now = next_wake
            for wake_at, fut in list(self._sleeps):
                if not fut.done() and wake_at <= self._now:
                    fut.set_result(None)
            for wake_at, cb, handle in list(self._later):
                if not handle.cancelled and wake_at <= self._now:
                    handle.cancelled = True
                    maybe = cb()
                    if inspect.isawaitable(maybe):
                        await maybe
            await asyncio.sleep(0)

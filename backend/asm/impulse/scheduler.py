from __future__ import annotations

import random
from datetime import date, datetime
from typing import Protocol

from asm.core.bus import EventBus
from asm.core.clock import SystemClock
from asm.core.events import ClientConnected, DialogState, MicState, ProactiveTrigger, StateChanged
from asm.core.interfaces import Clock
from asm.impulse.triggers import due_callbacks, idle_companion, session_open


class CompanionNotes(Protocol):
    def last_seen(self) -> datetime | None: ...

    def relationship_text(self) -> str: ...

    def self_state_text(self) -> str: ...


class ImpulseScheduler:
    def __init__(
        self,
        bus: EventBus,
        clock: Clock | None = None,
        notes: CompanionNotes | None = None,
        idle_s: float = 180,
        cooldown_s: float = 120,
        max_daily: int = 6,
        rng: random.Random | None = None,
    ) -> None:
        self.bus = bus
        self.clock = clock or SystemClock()
        self.notes = notes
        self.idle_s = idle_s
        self.cooldown_s = cooldown_s
        self.max_daily = max_daily
        self.rng = rng or random.Random()
        self._mic_open = False
        self._idle_since = self.clock.now()
        self._last_fire = 0.0
        self._daily = 0
        self._day = date.today()
        self._idle_timer = None
        bus.subscribe(StateChanged, self._on_state)
        bus.subscribe(MicState, self._on_mic)
        bus.subscribe(ClientConnected, self._on_client)

    async def _on_client(self, event: ClientConnected) -> None:
        del event
        await self.on_connect()

    async def on_connect(self) -> None:
        last = self.notes.last_seen() if self.notes else None
        trigger = session_open(last, datetime.now())
        await self._emit(trigger)
        rel = self.notes.relationship_text() if self.notes else ""
        for item in due_callbacks(rel, date.today()):
            await self._emit(item)
        self._idle_since = self.clock.now()
        self._idle_timer = self.clock.call_later(self.idle_s, self._on_idle)

    async def _on_mic(self, event: MicState) -> None:
        self._mic_open = event.open

    async def _on_state(self, event: StateChanged) -> None:
        if event.state == DialogState.IDLE:
            self._idle_since = self.clock.now()
            self._idle_timer = self.clock.call_later(self.idle_s, self._on_idle)
        else:
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None

    async def _on_idle(self) -> None:
        self._idle_timer = None
        idle_for = self.clock.now() - self._idle_since
        self_state = self.notes.self_state_text() if self.notes else ""
        trigger = idle_companion(idle_for, self._mic_open, self.idle_s, self_state, self.rng)
        if trigger:
            await self._emit(trigger)

    async def _emit(self, trigger) -> None:
        today = date.today()
        if today != self._day:
            self._day = today
            self._daily = 0
        if self._daily >= self.max_daily:
            return
        if self.clock.now() - self._last_fire < self.cooldown_s and self._last_fire > 0:
            return
        self._last_fire = self.clock.now()
        self._daily += 1
        await self.bus.publish(ProactiveTrigger(reason=trigger.reason, hint=trigger.hint))

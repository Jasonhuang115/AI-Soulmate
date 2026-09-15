from __future__ import annotations

import json
from pathlib import Path

from asm.core.bus import EventBus
from asm.core.events import LatencyMark


class LatencyLogger:
    def __init__(self, bus: EventBus, path: Path) -> None:
        self.path = path
        bus.subscribe(LatencyMark, self._on)

    async def _on(self, event: LatencyMark) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = {"turn_id": event.turn_id, **event.marks}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")

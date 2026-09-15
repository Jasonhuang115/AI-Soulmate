from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class Trigger:
    reason: str
    hint: str


def session_open(last_seen: datetime | None, now: datetime) -> Trigger:
    if last_seen is None:
        delta = "第一次见面"
    else:
        hours = max(int((now - last_seen).total_seconds() // 3600), 0)
        delta = f"距上次 {hours} 小时"
    return Trigger(reason="session_open", hint=delta)


def due_callbacks(relationship_text: str, today: date) -> list[Trigger]:
    found: list[Trigger] = []
    for match in re.finditer(r"截止日期:\s*(\d{4}-\d{2}-\d{2})", relationship_text):
        due = date.fromisoformat(match.group(1))
        if due <= today:
            found.append(Trigger(reason="callback", hint=match.group(0)))
    return found


def idle_companion(
    idle_seconds: float,
    mic_open: bool,
    threshold_s: float,
    self_state: str,
    rng: random.Random,
    probability: float = 0.3,
) -> Trigger | None:
    if not mic_open or idle_seconds < threshold_s:
        return None
    if rng.random() > probability:
        return None
    hint = self_state.strip().splitlines()[0] if self_state.strip() else "陪他待一会儿"
    return Trigger(reason="idle_companion", hint=hint)

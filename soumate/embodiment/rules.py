from __future__ import annotations

from dataclasses import dataclass
from random import Random

from .vocab import EMOTIONS, MOTIONS


@dataclass(frozen=True, slots=True)
class AppliedRule:
    expression: str | None
    motion: str | None


_RULES: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "neutral": ("neutral", ()),
    "happy": ("happy", ("laugh", "nod")),
    "shy": ("shy", ("look_away",)),
    "sad": ("sad", ()),
    "surprised": ("surprised", ("lean_in",)),
    "angry": ("angry", ()),
    "thinking": ("thinking", ("tilt",)),
    "playful": ("playful", ("wave",)),
    "agree": (None, ("nod",)),
    "disagree": (None, ("shake_head",)),
}


def apply_rule(
    emotion: str | None = None,
    intensity: float = 1.0,
    rng: Random | None = None,
    motion: str | None = None,
) -> AppliedRule:
    del intensity
    chosen = motion if motion in MOTIONS else None
    if not emotion:
        return AppliedRule(expression=None, motion=chosen)
    key = emotion if emotion in EMOTIONS else "neutral"
    expression, motions = _RULES[key]
    if chosen is None and motions:
        pick = rng or Random()
        chosen = pick.choice(list(motions))
    return AppliedRule(expression=expression, motion=chosen)

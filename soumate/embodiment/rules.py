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
    "happy": ("happy", ("wave", "clap", "jump")),
    "shy": ("shy", ("blush", "look_away")),
    "sad": ("sad", ("sad_pose",)),
    "surprised": ("surprised", ("surprise_pose", "jump")),
    "angry": ("angry", ("angry_pose",)),
    "thinking": ("thinking", ("think", "tilt")),
    "playful": ("playful", ("wave", "clap")),
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
        available = [name for name in motions if name in MOTIONS]
        if available:
            pick = rng or Random()
            chosen = pick.choice(available)
    return AppliedRule(expression=expression, motion=chosen)

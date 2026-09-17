from __future__ import annotations

from .catalog import gesture_names, prompt_motion_names

EMOTIONS = (
    "neutral",
    "happy",
    "shy",
    "sad",
    "surprised",
    "angry",
    "thinking",
    "playful",
    "agree",
    "disagree",
)

CONTROLS = ("stop",)

MOTIONS = gesture_names()
PROMPT_MOTIONS = prompt_motion_names()

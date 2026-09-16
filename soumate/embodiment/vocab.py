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

# Logical body motions. Files live in frontend/public/gestures/; missing clips no-op.
MOTIONS = gesture_names()
PROMPT_MOTIONS = prompt_motion_names()

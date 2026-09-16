from __future__ import annotations

import re

from .vocab import MOTIONS

_TAG = re.compile(r"⟦([a-z_]+)⟧|\[([a-z_]+)\]")
_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("wave", ("挥挥手", "挥下手", "挥个手", "招招手", "招下手", "招个手", "挥手", "招手", "wave")),
    ("clap", ("鼓鼓掌", "鼓个掌", "鼓掌", "clap")),
    ("think", ("想一想", "思考一下")),
    ("jump", ("跳一下", "跳一跳")),
    ("nod", ("点点头", "点个头", "点头", "nod")),
    ("shake_head", ("摇摇头", "摇个头", "摇头")),
    ("tilt", ("歪歪头", "歪个头", "歪头")),
    ("look_away", ("看别处", "躲开", "环顾")),
    ("lean_in", ("凑近点", "凑近")),
    ("laugh", ("笑一个", "笑一下")),
    ("bow", ("鞠个躬", "鞠躬")),
)


def infer_motion(text: str) -> str | None:
    for match in reversed(list(_TAG.finditer(text))):
        token = match.group(1) or match.group(2)
        if token in MOTIONS:
            return token
    lowered = text.lower()
    for motion, phrases in _PHRASES:
        for phrase in phrases:
            haystack = lowered if phrase.isascii() else text
            if phrase in haystack:
                return motion
    return None

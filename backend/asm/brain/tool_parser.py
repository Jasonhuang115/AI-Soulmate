from __future__ import annotations

import re
from dataclasses import dataclass

from embodiment.vocab import EMOTIONS, MOTIONS

# Canonical: ⟦happy⟧ / ⟦wave⟧. Also accept [happy] and leftover [key=happy] so TTS never reads them.
TAG_RE = re.compile(r"⟦([a-z_]+)⟧|\[([a-z_]+)=([a-z_]+)\]|\[([a-z_]+)\]")
INCOMPLETE_TAIL = re.compile(r"(?:⟦[a-z_]*|\[[a-z_]+(?:=[a-z_]*)?|\[)$")
_EMOTIONS = frozenset(EMOTIONS)
_MOTIONS = frozenset(MOTIONS)


@dataclass(frozen=True, slots=True)
class Marker:
    kind: str
    name: str


def classify_token(name: str) -> Marker | None:
    if name in _EMOTIONS:
        return Marker("emotion", name)
    if name in _MOTIONS:
        return Marker("motion", name)
    return None


def strip_emotion_markers(text: str) -> tuple[str, list[Marker]]:
    found: list[Marker] = []

    def repl(match: re.Match[str]) -> str:
        boxed = match.group(1)
        keyed = match.group(3)
        bare = match.group(4)
        token = boxed if boxed is not None else keyed if keyed is not None else bare
        marker = classify_token(token) if token else None
        if boxed is not None or keyed is not None:
            if marker:
                found.append(marker)
            return ""
        if marker:
            found.append(marker)
            return ""
        return match.group(0)

    cleaned = TAG_RE.sub(repl, text)
    return cleaned, found


def group_markers(markers: list[Marker]) -> list[tuple[str | None, str | None]]:
    groups: list[tuple[str | None, str | None]] = []
    emotion: str | None = None
    motion: str | None = None
    open_group = False
    for marker in markers:
        if marker.kind == "emotion":
            if open_group:
                groups.append((emotion, motion))
            emotion, motion = marker.name, None
            open_group = True
            continue
        if not open_group:
            emotion, motion = None, marker.name
            open_group = True
            continue
        motion = marker.name
    if open_group:
        groups.append((emotion, motion))
    return groups


class EmotionStripper:
    def __init__(self) -> None:
        self._buf = ""

    def feed(self, text: str) -> tuple[str, list[Marker]]:
        self._buf += text
        leftover = _incomplete_suffix(self._buf)
        if leftover:
            complete = self._buf[: -len(leftover)]
            self._buf = leftover
            return strip_emotion_markers(complete)
        cleaned, markers = strip_emotion_markers(self._buf)
        self._buf = ""
        return cleaned, markers

    def flush(self) -> tuple[str, list[Marker]]:
        cleaned, markers = strip_emotion_markers(self._buf)
        self._buf = ""
        return cleaned, markers


def _incomplete_suffix(text: str) -> str:
    match = INCOMPLETE_TAIL.search(text)
    if not match or match.end() != len(text):
        return ""
    return match.group(0)

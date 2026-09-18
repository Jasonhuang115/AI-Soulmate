from __future__ import annotations

import re
from dataclasses import dataclass

from embodiment.resolve import classify, log_unresolved

TAG_RE = re.compile(
    r"⟦此刻([^⟦⟧]*)⟧|⟦([a-z_]+)⟧|\[([a-z_]+)=([a-z_]+)\]|\[([a-z_]+)\]"
)
INCOMPLETE_TAIL = re.compile(r"(?:⟦[^⟧]*|\[[a-z_]+(?:=[a-z_]*)?|\[)$")
MAX_MOTIONS = 3
NOW_MAX_CHARS = 40
_SCALE_WORDS = ("valence", "arousal", "PAD", "intensity", "好感度", "心情值", "效价", "唤醒")
_SCALE_RE = re.compile(r"(?:\d+\.\d+|\d+\s*/\s*\d+|\d+分)")


@dataclass(frozen=True, slots=True)
class Marker:
    kind: str
    name: str


@dataclass(frozen=True, slots=True)
class TagSet:
    emotion: str | None = None
    motions: tuple[str, ...] = ()
    control: str | None = None

    @property
    def empty(self) -> bool:
        return not self.emotion and not self.motions and not self.control


def classify_token(name: str) -> Marker | None:
    hit = classify(name)
    if hit is None:
        return None
    return Marker(hit[0], hit[1])


def sanitize_now_body(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    for index, char in enumerate(text):
        if char in "。！？":
            text = text[: index + 1]
            break
    if len(text) > NOW_MAX_CHARS:
        text = text[:NOW_MAX_CHARS]
    if any(word in text for word in _SCALE_WORDS):
        return None
    if _SCALE_RE.search(text):
        return None
    return text or None


def last_now_body(text: str) -> str | None:
    found: str | None = None
    for part in parse_parts(text):
        if isinstance(part, Marker) and part.kind == "now" and part.name:
            found = part.name
    return found


def parse_parts(text: str) -> list[str | Marker]:
    parts: list[str | Marker] = []
    last = 0
    for match in TAG_RE.finditer(text):
        if match.start() > last:
            parts.append(text[last : match.start()])
        if match.group(0).startswith("⟦此刻"):
            body = sanitize_now_body(match.group(1) or "")
            if body:
                parts.append(Marker("now", body))
            last = match.end()
            continue
        boxed = match.group(2)
        keyed = match.group(4)
        bare = match.group(5)
        token = boxed if boxed is not None else keyed if keyed is not None else bare
        marker = classify_token(token) if token else None
        if boxed is not None or keyed is not None:
            if marker:
                parts.append(marker)
            elif boxed is not None and token:
                log_unresolved(token)
        elif marker:
            parts.append(marker)
        else:
            parts.append(match.group(0))
        last = match.end()
    if last < len(text):
        parts.append(text[last:])
    return parts


def strip_emotion_markers(text: str) -> tuple[str, list[Marker]]:
    parts = parse_parts(text)
    cleaned = "".join(part for part in parts if isinstance(part, str))
    markers = [part for part in parts if isinstance(part, Marker)]
    return cleaned, markers


def collect_tags(markers: list[Marker], max_motions: int = MAX_MOTIONS) -> TagSet:
    emotion: str | None = None
    motions: list[str] = []
    control: str | None = None
    for marker in markers:
        if marker.kind == "emotion":
            emotion = marker.name
        elif marker.kind == "motion":
            if len(motions) < max_motions:
                motions.append(marker.name)
        elif marker.kind == "control":
            control = marker.name
    return TagSet(emotion=emotion, motions=tuple(motions), control=control)


def group_markers(markers: list[Marker]) -> list[tuple[str | None, str | None]]:
    tags = collect_tags(markers)
    if tags.empty:
        return []
    motion = tags.motions[0] if tags.motions else None
    return [(tags.emotion, motion)]


class EmotionStripper:
    def __init__(self) -> None:
        self._buf = ""

    def feed(self, text: str) -> tuple[str, list[Marker]]:
        parts = self.feed_parts(text)
        cleaned = "".join(part for part in parts if isinstance(part, str))
        markers = [part for part in parts if isinstance(part, Marker)]
        return cleaned, markers

    def feed_parts(self, text: str) -> list[str | Marker]:
        self._buf += text
        leftover = _incomplete_suffix(self._buf)
        if leftover:
            complete = self._buf[: -len(leftover)]
            self._buf = leftover
            return parse_parts(complete)
        parts = parse_parts(self._buf)
        self._buf = ""
        return parts

    def flush(self) -> tuple[str, list[Marker]]:
        parts = self.flush_parts()
        cleaned = "".join(part for part in parts if isinstance(part, str))
        markers = [part for part in parts if isinstance(part, Marker)]
        return cleaned, markers

    def flush_parts(self) -> list[str | Marker]:
        leftover = _incomplete_suffix(self._buf)
        complete = self._buf[: -len(leftover)] if leftover else self._buf
        self._buf = ""
        return parse_parts(complete)


def _incomplete_suffix(text: str) -> str:
    match = INCOMPLETE_TAIL.search(text)
    if not match or match.end() != len(text):
        return ""
    return match.group(0)

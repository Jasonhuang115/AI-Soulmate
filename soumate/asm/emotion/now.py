from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from asm.brain.tool_parser import last_now_body


@dataclass(frozen=True, slots=True)
class NowMood:
    text: str
    written_at: datetime
    source_turn: str


def parse_self_state_text(raw: str) -> NowMood | None:
    body = ""
    written: datetime | None = None
    source = ""
    for line in raw.splitlines():
        if line.startswith("此刻："):
            body = line.removeprefix("此刻：").strip()
        elif line.startswith("写下："):
            stamp = line.removeprefix("写下：").strip()
            try:
                written = datetime.fromisoformat(stamp)
            except ValueError:
                written = None
        elif line.startswith("来源："):
            source = line.removeprefix("来源：").strip()
    if not body or written is None:
        return None
    return NowMood(text=body, written_at=written, source_turn=source)


def render_self_state(mood: NowMood) -> str:
    stamp = mood.written_at.isoformat(timespec="seconds")
    return f"此刻：{mood.text}\n写下：{stamp}\n来源：{mood.source_turn}\n"


def now_body_from_file(raw: str, now: datetime | None = None) -> str:
    mood = parse_self_state_text(raw)
    if mood is None:
        return ""
    if now is not None and mood.written_at.date() < now.date():
        return ""
    return mood.text


def ago_label(written_at: datetime, now: datetime) -> str:
    minutes = max(int((now - written_at).total_seconds() // 60), 0)
    if minutes < 1:
        return "刚刚"
    return f"{minutes} 分钟前"


def since_label(written_at: datetime, now: datetime) -> str:
    seconds = max((now - written_at).total_seconds(), 0)
    hours = int(seconds // 3600)
    if hours < 1:
        minutes = int(seconds // 60)
        return f"{minutes} 分钟"
    return f"{hours} 小时"


class NowStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.mood: NowMood | None = None
        self.reunion = False
        self.cut_pending = False
        self._wrote_now = False
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            self.mood = None
            return
        self.mood = parse_self_state_text(self.path.read_text(encoding="utf-8"))

    def _write(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")

    def save(self) -> None:
        if self.mood is None:
            self._write("")
            return
        self._write(render_self_state(self.mood))

    def clear(self) -> None:
        self.mood = None
        self.reunion = False
        self._write("")

    def expire_if_stale(self, now: datetime) -> None:
        if self.mood is not None and self.mood.written_at.date() < now.date():
            self.clear()

    def live_body(self, now: datetime | None = None) -> str:
        if now is not None:
            self.expire_if_stale(now)
        if self.mood is None:
            return ""
        return self.mood.text

    def mark_reunion(self, now: datetime) -> None:
        self.expire_if_stale(now)
        self.reunion = self.mood is not None

    def mark_mid_speech_cut(self) -> None:
        self.cut_pending = True

    def commit(self, text: str, turn_id: str, at: datetime) -> None:
        self.mood = NowMood(text=text, written_at=at, source_turn=turn_id)
        self.reunion = False
        self.save()

    def commit_from_raw(self, raw_text: str, turn_id: str, at: datetime) -> None:
        body = last_now_body(raw_text)
        if not body:
            return
        self.commit(body, turn_id, at)
        self._wrote_now = True

    def after_successful_turn(self) -> None:
        wrote = self._wrote_now
        self._wrote_now = False
        if self.reunion and not wrote:
            self.clear()
        else:
            self.reunion = False
        self.cut_pending = False

    def situation_kwargs(self, now: datetime) -> dict[str, object]:
        self.expire_if_stale(now)
        return {
            "now_mood": self.mood,
            "reunion": bool(self.reunion and self.mood is not None),
            "mid_speech_cut": self.cut_pending,
        }

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from asm.core.interfaces import Message, PromptContext
from embodiment.vocab import EMOTIONS, MOTIONS
from embodiment.catalog import format_motion_groups

REQUIRED_SECTIONS = ("soul", "medium", "tools")


@dataclass(frozen=True, slots=True)
class PromptFragment:
    name: str
    body: str

    @property
    def section_name(self) -> str:
        stem = self.name
        if len(stem) >= 3 and stem[:2].isdigit() and stem[2] == "-":
            stem = stem[3:]
        return stem.replace("-", "_")


def soumate_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_prompts_dir() -> Path:
    return soumate_root() / "prompts"


def resolve_prompts_dir(value: str | Path | None = None) -> Path:
    if value is None:
        return default_prompts_dir()
    path = Path(value)
    if path.is_absolute():
        return path
    return soumate_root() / path


def load_prompt_fragments(directory: Path | None = None) -> list[PromptFragment]:
    folder = directory if directory is not None else default_prompts_dir()
    if not folder.is_dir():
        raise FileNotFoundError(f"prompts directory missing: {folder}")
    fragments = [
        PromptFragment(name=path.stem, body=path.read_text(encoding="utf-8"))
        for path in sorted(folder.glob("*.md"))
    ]
    names = {item.section_name for item in fragments}
    missing = [name for name in REQUIRED_SECTIONS if name not in names]
    if missing:
        raise FileNotFoundError(f"missing prompt sections {missing} in {folder}")
    return fragments


def emotion_markers() -> str:
    return " ".join(f"⟦{name}⟧" for name in EMOTIONS)


def motion_markers() -> str:
    return " ".join(f"⟦{name}⟧" for name in MOTIONS)


def motion_group_hint() -> str:
    return format_motion_groups()


def assemble_framework(directory: Path | None = None) -> str:
    sections: list[str] = []
    emotions = emotion_markers()
    motions = motion_markers()
    groups = motion_group_hint()
    for fragment in load_prompt_fragments(directory):
        tag = fragment.section_name
        body = (
            fragment.body.strip()
            .replace("{emotion_markers}", emotions)
            .replace("{motion_markers}", motions)
            .replace("{motion_group_hint}", groups)
        )
        sections.append(f"<{tag}>\n{body}\n</{tag}>")
    return "\n\n".join(sections)


def build_messages(
    context: PromptContext,
    session_summary: str,
    situation: str,
    history: list[Message] | tuple[Message, ...],
    user_text: str,
    prompts_dir: Path | None = None,
) -> list[Message]:
    parts: list[Message] = [Message(role="system", content=assemble_framework(prompts_dir))]
    if context.index.strip():
        parts.append(Message(role="system", content=f"长期记忆：\n{context.index.strip()}"))
    if session_summary.strip():
        parts.append(
            Message(
                role="system",
                content="近期脉络：\n更早的聊天已折进下面，自然接上，不要向用户提起摘要。\n"
                + session_summary.strip(),
            )
        )
    if situation.strip():
        parts.append(Message(role="system", content=f"情境：\n{situation.strip()}"))
    parts.extend(history)
    parts.append(Message(role="user", content=user_text))
    return parts


def format_situation(now: datetime, last_chat_at: datetime | None = None) -> str:
    weekday = "一二三四五六日"[now.weekday()]
    line = f"现在是 {now:%Y-%m-%d} 星期{weekday} {now:%H:%M}。"
    if last_chat_at is not None:
        delta = now - last_chat_at
        hours = max(int(delta.total_seconds() // 3600), 0)
        line += f" 距上次聊天大约 {hours} 小时。"
    return line

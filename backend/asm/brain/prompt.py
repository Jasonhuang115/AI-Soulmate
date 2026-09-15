from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from asm.core.interfaces import Message, PromptContext
from embodiment.vocab import EMOTIONS, MOTIONS

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


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_prompts_dir() -> Path:
    return repo_root() / "prompts"


def resolve_prompts_dir(value: str | Path | None = None) -> Path:
    if value is None:
        return default_prompts_dir()
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root() / path


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


def assemble_framework(directory: Path | None = None) -> str:
    sections: list[str] = []
    emotions = emotion_markers()
    motions = motion_markers()
    for fragment in load_prompt_fragments(directory):
        tag = fragment.section_name
        body = (
            fragment.body.strip()
            .replace("{emotion_markers}", emotions)
            .replace("{motion_markers}", motions)
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
    resident = "\n\n".join(
        block
        for block in (
            context.index,
            context.relationship,
            context.self_state,
        )
        if block.strip()
    )
    if resident:
        parts.append(Message(role="system", content=f"长期记忆：\n{resident}"))
    if session_summary.strip():
        parts.append(Message(role="system", content=f"本次会话摘要：\n{session_summary.strip()}"))
    snippets = "\n".join(context.snippets)
    situation_block = situation.strip()
    if snippets:
        situation_block = f"{situation_block}\n相关记忆：\n{snippets}".strip()
    if situation_block:
        parts.append(Message(role="system", content=f"情境：\n{situation_block}"))
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

from __future__ import annotations

import re

_FILLERS = frozenset("嗯啊额哦唔。，,!?！？… \t\n　~～")

_PHATIC = re.compile(
    r"^(?:"
    r"你好[啊呀嘛吗]?"
    r"|您好"
    r"|嗨+"
    r"|哈喽"
    r"|hello|hi|hey"
    r"|早[安上]?"
    r"|早上好|晚安"
    r"|在吗|在嘛|在不在"
    r"|谢谢你?"
    r"|thank(?:s| you)?"
    r"|哈哈+"
    r"|嘿嘿+"
    r")[\s,.!！。?？…~～]*$",
    re.IGNORECASE,
)


def meaningful_len(text: str) -> int:
    return sum(1 for ch in text if ch not in _FILLERS)


def is_system_turn(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("[系统：") or stripped.startswith("[系统:")


def is_phatic(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if is_system_turn(stripped):
        return True
    if _PHATIC.fullmatch(stripped):
        return True
    return meaningful_len(stripped) < 4


def skip_recall(text: str, last: str = "") -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped == last.strip():
        return True
    return is_phatic(stripped)


def skip_extract(rows: list[dict]) -> bool:
    users = [(row.get("user") or "") for row in rows]
    if not any(item.strip() for item in users):
        return True
    return all(is_phatic(item) for item in users)

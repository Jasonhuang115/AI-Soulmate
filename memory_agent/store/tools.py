from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .paths import resolve_under

MEMORY_MAX_LINES = 200
MEMORY_MAX_BYTES = 25 * 1024

TYPE_FILES = frozenset(
    {"user.md", "relationship.md", "boundaries.md", "threads.md"}
)
WRITABLE_FILES = TYPE_FILES | {"MEMORY.md"}
_HIDDEN_NAMES = frozenset({"rolling.md", "persona.md", "self_state.md"})


def _is_hidden_rel(rel: str) -> bool:
    rel = normalize_rel(rel)
    name = Path(rel).name
    if not rel or rel == ".":
        return False
    if name.startswith("."):
        return True
    if name in _HIDDEN_NAMES:
        return True
    if name.endswith(".sqlite") or ".sqlite-" in name:
        return True
    if rel == "logs" or rel.startswith("logs/"):
        return True
    if rel.startswith("user/"):
        return True
    return False


def memory_overflow(content: str) -> str | None:
    lines = content.splitlines()
    if len(lines) > MEMORY_MAX_LINES:
        return (
            f"MEMORY.md is {len(lines)} lines (max {MEMORY_MAX_LINES}); "
            "delete first then write"
        )
    size = len(content.encode("utf-8"))
    if size > MEMORY_MAX_BYTES:
        return (
            f"MEMORY.md is {size} bytes (max {MEMORY_MAX_BYTES}); "
            "delete first then write"
        )
    return None


def normalize_rel(rel: str) -> str:
    return rel.replace("\\", "/").lstrip("./")


class MemoryTools:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def ls(self, rel: str = ".") -> list[str]:
        path = resolve_under(self.root, rel)
        if not path.exists():
            return []
        if path.is_file():
            mapped = normalize_rel(rel)
            if _is_hidden_rel(mapped):
                return []
            return [mapped]
        return sorted(
            str(p.relative_to(self.root))
            for p in path.rglob("*")
            if p.is_file() and not _is_hidden_rel(str(p.relative_to(self.root)))
        )

    def read(self, rel: str) -> str:
        path = resolve_under(self.root, rel)
        if not path.is_file() or _is_hidden_rel(rel):
            return ""
        return path.read_text(encoding="utf-8")

    def grep(self, pattern: str, rel: str = ".") -> list[str]:
        rx = re.compile(pattern)
        hits: list[str] = []
        for name in self.ls(rel):
            text = self.read(name)
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{name}:{i}:{line}")
                    if len(hits) >= 50:
                        return hits
        return hits

    def write(self, rel: str, content: str) -> None:
        rel = self._guard_write(rel)
        if rel == "MEMORY.md":
            overflow = memory_overflow(content)
            if overflow:
                raise ValueError(overflow)
        path = resolve_under(self.root, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = content if content.endswith("\n") or not content else content + "\n"
        path.write_text(text, encoding="utf-8")
        self._log(rel, "write", f"{len(text)} chars")

    def write_section(self, rel: str, heading: str, body: str) -> None:
        rel = self._guard_write(rel)
        path = resolve_under(self.root, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        section = f"## {heading}\n{body.rstrip()}\n"
        marker = f"## {heading}"
        if marker in current:
            parts = re.split(r"(?=^## )", current, flags=re.M)
            rewritten = []
            for part in parts:
                if part.startswith(marker):
                    rewritten.append(section)
                elif part.strip():
                    rewritten.append(part if part.endswith("\n") else part + "\n")
            text = "".join(rewritten)
        else:
            prefix = current.rstrip() + "\n\n" if current.strip() else ""
            text = prefix + section
        if rel == "MEMORY.md":
            overflow = memory_overflow(text)
            if overflow:
                raise ValueError(overflow)
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        self._log(rel, "write_section", heading)

    def _guard_write(self, rel: str) -> str:
        rel = normalize_rel(rel)
        if rel.startswith(".") or _is_hidden_rel(rel):
            raise PermissionError(f"memory agent cannot write {rel}")
        if rel not in WRITABLE_FILES:
            raise PermissionError(f"cannot write {rel}")
        return rel

    def _log(self, rel: str, op: str, detail: str) -> None:
        line = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "op": op,
            "path": rel,
            "detail": detail,
        }
        changelog = self.root / ".changelog.jsonl"
        with changelog.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")

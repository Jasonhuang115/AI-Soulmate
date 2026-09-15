from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .paths import resolve_under


class MemoryTools:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def ls(self, rel: str = ".") -> list[str]:
        path = resolve_under(self.root, rel)
        if not path.exists():
            return []
        if path.is_file():
            return [rel]
        return sorted(str(p.relative_to(self.root)) for p in path.rglob("*") if p.is_file())

    def read(self, rel: str) -> str:
        path = resolve_under(self.root, rel)
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def grep(self, pattern: str, rel: str = ".") -> list[str]:
        rx = re.compile(pattern)
        hits: list[str] = []
        for name in self.ls(rel):
            if name.endswith(".jsonl") and "transcripts" in name:
                pass
            text = self.read(name)
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{name}:{i}:{line}")
                    if len(hits) >= 50:
                        return hits
        return hits

    def write_section(self, rel: str, heading: str, body: str) -> None:
        path = resolve_under(self.root, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        section = f"## {heading}\n{body.rstrip()}\n"
        marker = f"## {heading}"
        if marker in current:
            parts = re.split(rf"(?=^## )", current, flags=re.M)
            rewritten = []
            for part in parts:
                if part.startswith(marker):
                    rewritten.append(section)
                elif part.strip():
                    rewritten.append(part if part.endswith("\n") else part + "\n")
            path.write_text("".join(rewritten), encoding="utf-8")
        else:
            prefix = current.rstrip() + "\n\n" if current.strip() else ""
            path.write_text(prefix + section, encoding="utf-8")
        self._log(rel, "write_section", heading)

    def append(self, rel: str, text: str) -> None:
        if not rel.startswith("logs/"):
            raise PermissionError("append is only allowed under logs/")
        path = resolve_under(self.root, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text.rstrip() + "\n")
        self._log(rel, "append", text[:80])

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

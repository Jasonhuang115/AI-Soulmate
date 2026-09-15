from __future__ import annotations

from datetime import datetime
from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for path in (here, *here.parents):
        if (path / "pyproject.toml").exists():
            return path
    raise RuntimeError("cannot find repo root")


def default_memdir() -> Path:
    return repo_root() / "data" / "memory"


def resolve_under(root: Path, rel: str) -> Path:
    if rel.startswith("/"):
        raise ValueError("absolute paths are not allowed")
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError(f"path escapes memory dir: {rel}")
    return target


def read_last_seen(path: Path) -> datetime | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.fromisoformat(raw + "T00:00:00")
        except ValueError:
            return None

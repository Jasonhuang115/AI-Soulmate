from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .catalog import alias_map, repo_root
from .vocab import CONTROLS, EMOTIONS, MOTIONS


def _normalize(name: str) -> str:
    return name.strip().lower().replace("-", "_")


def classify(name: str) -> tuple[str, str] | None:
    token = _normalize(name)
    if not token:
        return None
    if token in EMOTIONS:
        return ("emotion", token)
    if token in CONTROLS:
        return ("control", token)
    mapped = alias_map().get(token)
    if mapped in MOTIONS:
        return ("motion", mapped)
    if token in MOTIONS:
        return ("motion", token)
    return None


def unresolved_log_path() -> Path:
    return repo_root() / "data/logs/unresolved_markers.jsonl"


def log_unresolved(name: str, path: Path | None = None) -> None:
    dest = path if path is not None else unresolved_log_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat(), "name": name}
    with dest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

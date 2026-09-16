from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def catalog_path() -> Path:
    return repo_root() / "frontend/public/gestures/catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    path = catalog_path()
    if not path.is_file():
        return {"prompt_phase": 1, "idle": "idle_loop.vrma", "gestures": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def gestures() -> dict[str, dict[str, Any]]:
    raw = load_catalog().get("gestures") or {}
    return {str(name): dict(spec) for name, spec in raw.items()}


def prompt_phase() -> int:
    try:
        return int(load_catalog().get("prompt_phase") or 1)
    except (TypeError, ValueError):
        return 1


def gesture_names() -> tuple[str, ...]:
    return tuple(gestures())


def prompt_motion_names() -> tuple[str, ...]:
    phase = prompt_phase()
    names: list[str] = []
    for name, spec in gestures().items():
        if spec.get("prompt") is False:
            continue
        try:
            item_phase = int(spec.get("phase") or 1)
        except (TypeError, ValueError):
            item_phase = 1
        if item_phase <= phase:
            names.append(name)
    return tuple(names)


def motion_groups() -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    allowed = set(prompt_motion_names())
    for name, spec in gestures().items():
        if name not in allowed:
            continue
        group = str(spec.get("group") or "other")
        grouped.setdefault(group, []).append(name)
    return {key: tuple(value) for key, value in grouped.items()}


def format_motion_groups() -> str:
    lines: list[str] = []
    labels = {
        "greet": "打招呼",
        "agree": "同意反对",
        "think": "思考",
        "body": "身体姿态",
        "react": "反应",
        "idle": "待机",
        "other": "其他",
    }
    for key, names in motion_groups().items():
        title = labels.get(key, key)
        joined = " ".join(f"⟦{name}⟧" for name in names)
        lines.append(f"{title}：{joined}")
    if not lines:
        return ""
    return "动作分组（每句最多再带一个）：\n" + "\n".join(lines)


def scan_vrma_stems(directory: Path | None = None) -> set[str]:
    folder = directory if directory is not None else catalog_path().parent
    if not folder.is_dir():
        return set()
    return {path.stem for path in folder.glob("*.vrma")}

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
        return {"idle": "idle_loop.vrma", "gestures": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def gestures() -> dict[str, dict[str, Any]]:
    raw = load_catalog().get("gestures") or {}
    return {str(name): dict(spec) for name, spec in raw.items()}


def gesture_names() -> tuple[str, ...]:
    return tuple(gestures())


def prompt_motion_names() -> tuple[str, ...]:
    return gesture_names()


def motion_kind(name: str) -> str:
    spec = gestures().get(name) or {}
    return str(spec.get("kind") or "gesture")


def motion_holds(name: str) -> str | None:
    spec = gestures().get(name) or {}
    holds = spec.get("holds")
    return str(holds) if holds else None


def motion_face(name: str) -> str | None:
    spec = gestures().get(name) or {}
    face = spec.get("face")
    return str(face) if face else None


def alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for name, spec in gestures().items():
        mapping[name] = name
        mapping[name.replace("-", "_")] = name
        for alias in spec.get("aliases") or []:
            mapping[str(alias).replace("-", "_")] = name
    return mapping


def motion_groups() -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for name, spec in gestures().items():
        group = str(spec.get("group") or "other")
        grouped.setdefault(group, []).append(name)
    return {key: tuple(value) for key, value in grouped.items()}


def format_motion_groups() -> str:
    labels = {
        "greet": "打招呼",
        "agree": "同意反对",
        "think": "思考",
        "body": "身体姿态",
        "react": "反应",
        "idle": "待机",
        "other": "其他",
    }
    lines: list[str] = []
    for key, names in motion_groups().items():
        title = labels.get(key, key)
        bits: list[str] = []
        for name in names:
            spec = gestures()[name]
            desc = str(spec.get("desc") or spec.get("label") or name)
            bits.append(f"⟦{name}⟧{desc}")
        lines.append(f"{title}：{' '.join(bits)}")
    if not lines:
        return ""
    return "动作（用户点名写在句首，自己加戏才写句末；默认不写）：\n" + "\n".join(lines)


def scan_vrma_stems(directory: Path | None = None) -> set[str]:
    folder = directory if directory is not None else catalog_path().parent
    if not folder.is_dir():
        return set()
    return {path.stem for path in folder.glob("*.vrma")}

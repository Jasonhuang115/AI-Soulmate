#!/usr/bin/env python3
"""Map Motifect BVH clips onto catalog keys and convert them to .vrma."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bvh_to_vrma import convert_file, inspect_vrma  # noqa: E402
from gesture_sources import GESTURE_SOURCES, assert_unique_sources  # noqa: E402

CATALOG = ROOT / "frontend/public/gestures/catalog.json"
DEST = CATALOG.parent
UNPACKED = ROOT / "data/mixamo/unpacked"


def resolve_bvh(source: str) -> Path:
    pack, filename = source.split("/", 1)
    return UNPACKED / pack / "BVH" / filename


def write_catalog(catalog: dict) -> None:
    gestures = catalog.get("gestures") or {}
    lines = [
        "{",
        f'  "prompt_phase": {int(catalog.get("prompt_phase") or 3)},',
        f'  "default_model": {json.dumps(catalog.get("default_model") or "/models/vrm/default.vrm")},',
        f'  "idle": {json.dumps(catalog.get("idle") or "idle_loop.vrma")},',
        '  "gestures": {',
    ]
    items = list(gestures.items())
    for index, (name, spec) in enumerate(items):
        payload = json.dumps(spec, ensure_ascii=False, separators=(", ", ": "))
        comma = "," if index < len(items) - 1 else ""
        lines.append(f'    "{name}": {payload}{comma}')
    lines.extend(["  }", "}", ""])
    CATALOG.write_text("\n".join(lines), encoding="utf-8")


def patch_catalog() -> dict:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    catalog["prompt_phase"] = 3
    gestures = catalog.get("gestures") or {}
    for name, source in GESTURE_SOURCES.items():
        spec = gestures.get(name)
        if not spec:
            raise KeyError(f"catalog missing gesture {name}")
        spec["source"] = source
    write_catalog(catalog)
    return catalog


def main() -> int:
    assert_unique_sources()
    catalog = patch_catalog()
    gestures = catalog.get("gestures") or {}
    missing_src: list[str] = []
    converted = 0
    skipped = 0
    failed: list[str] = []
    weak: list[str] = []
    force = "--force" in sys.argv
    for name, spec in gestures.items():
        source = spec.get("source")
        filename = spec.get("file")
        if not source or not filename:
            continue
        dest = DEST / filename
        src = resolve_bvh(source)
        if not src.is_file():
            missing_src.append(f"{name} -> {source}")
            continue
        if dest.is_file() and dest.stat().st_size > 0 and not force:
            skipped += 1
            try:
                info = inspect_vrma(dest)
                if info["bones"] < 20 or info["duration"] < 0.25:
                    weak.append(f"{name} bones={info['bones']} duration={info['duration']:.2f}")
            except Exception as exc:  # noqa: BLE001
                weak.append(f"{name} inspect {exc}")
            continue
        try:
            info = convert_file(src, dest, in_place=True)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{name}: {exc}")
            dest.unlink(missing_ok=True)
            continue
        converted += 1
        if info["bones"] < 20 or info["duration"] < 0.25:
            weak.append(f"{name} bones={info['bones']} duration={info['duration']:.2f}")
            dest.unlink(missing_ok=True)
            failed.append(f"{name}: quality filter")
            converted -= 1
            continue
        print(f"ok {name:16} bones={info['bones']:2} {info['duration']:.2f}s <- {source}")

    print(f"converted={converted} reused={skipped}")
    if missing_src:
        print("missing source files:")
        for line in missing_src:
            print(f"  {line}")
    if failed:
        print("failed:")
        for line in failed:
            print(f"  {line}")
    if weak:
        print("weak:")
        for line in weak:
            print(f"  {line}")
    return 1 if failed or missing_src else 0


if __name__ == "__main__":
    raise SystemExit(main())

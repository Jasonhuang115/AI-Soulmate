#!/usr/bin/env python3
"""Scan public/gestures/*.vrma and print coverage against catalog.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "frontend/public/gestures/catalog.json"
GESTURES = CATALOG.parent


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    present = {path.name for path in GESTURES.glob("*.vrma")}
    idle = catalog.get("idle")
    gestures = catalog.get("gestures") or {}
    by_phase: dict[int, list[str]] = {}
    missing: list[str] = []
    for name, spec in gestures.items():
        phase = int(spec.get("phase") or 1)
        by_phase.setdefault(phase, []).append(name)
        filename = spec.get("file")
        if filename and filename not in present:
            missing.append(f"phase{phase} {name} -> {filename}")
    print(f"vrma files on disk: {len(present)}")
    if idle:
        print(f"idle: {idle} {'ok' if idle in present else 'MISSING'}")
    for phase in sorted(by_phase):
        names = by_phase[phase]
        ready = sum(1 for name in names if (gestures[name].get("file") or "") in present)
        print(f"phase {phase}: {ready}/{len(names)} files")
    if missing:
        print("missing clips:")
        for line in missing[:30]:
            print(f"  {line}")
        if len(missing) > 30:
            print(f"  … {len(missing) - 30} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())

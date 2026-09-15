from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path


class DreamGate:
    """File lock plus last_run cursor. No 24h / session-count gate."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock_path = root / ".dream-lock"
        self.last_run_path = root / ".last_run"

    def last_run(self) -> str | None:
        if not self.last_run_path.is_file():
            return None
        text = self.last_run_path.read_text(encoding="utf-8").strip()
        return text or None

    def mark_run(self, when: datetime | str | None = None) -> None:
        if isinstance(when, str) and when.strip():
            stamp = when.strip()
        elif isinstance(when, datetime):
            stamp = when.isoformat(timespec="seconds")
        else:
            stamp = datetime.now().isoformat(timespec="seconds")
        self.last_run_path.write_text(stamp + "\n", encoding="utf-8")

    def try_acquire(self) -> bool:
        if self.lock_path.exists():
            try:
                pid = int(self.lock_path.read_text(encoding="utf-8").strip() or "0")
            except ValueError:
                pid = 0
            if pid and _pid_alive(pid) and (time.time() - self.lock_path.stat().st_mtime) < 3600:
                return False
        self.lock_path.write_text(str(os.getpid()), encoding="utf-8")
        return True

    def release(self) -> None:
        if self.lock_path.exists():
            self.lock_path.write_text("", encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True

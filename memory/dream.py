from __future__ import annotations

import os
import time
from pathlib import Path


class DreamGate:
    def __init__(self, root: Path, min_hours: float = 24, min_sessions: int = 5) -> None:
        self.root = root
        self.min_hours = min_hours
        self.min_sessions = min_sessions
        self.lock_path = root / ".dream-lock"
        self.sessions_path = root / ".sessions"

    def session_count_since_lock(self) -> int:
        if not self.sessions_path.exists():
            return 0
        last = self.lock_path.stat().st_mtime if self.lock_path.exists() else 0
        count = 0
        for line in self.sessions_path.read_text(encoding="utf-8").splitlines():
            try:
                if float(line) > last:
                    count += 1
            except ValueError:
                continue
        return count

    def note_session(self) -> None:
        with self.sessions_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.time()}\n")

    def should_run(self) -> bool:
        if self.lock_path.exists():
            age_h = (time.time() - self.lock_path.stat().st_mtime) / 3600
            if age_h < self.min_hours:
                return False
        return self.session_count_since_lock() >= self.min_sessions

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

    def mark_success(self) -> None:
        self.lock_path.touch()
        self.lock_path.write_text(str(os.getpid()), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True

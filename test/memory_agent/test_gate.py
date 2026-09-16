from pathlib import Path

from memory_agent.store.gate import DreamGate


def test_last_run_starts_empty(tmp_path: Path) -> None:
    gate = DreamGate(tmp_path)
    assert gate.last_run() is None
    gate.mark_run("2026-09-16T12:00:00")
    assert gate.last_run() == "2026-09-16T12:00:00"


def test_lock_blocks_live_pid(tmp_path: Path) -> None:
    gate = DreamGate(tmp_path)
    gate.try_acquire()
    other = DreamGate(tmp_path)
    assert other.try_acquire() is False
    gate.release()
    assert other.try_acquire() is True

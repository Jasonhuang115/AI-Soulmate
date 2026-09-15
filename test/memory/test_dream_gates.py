from pathlib import Path

from memory.dream import DreamGate


def test_gates_need_sessions_and_time(tmp_path: Path) -> None:
    gate = DreamGate(tmp_path, min_hours=24, min_sessions=2)
    assert gate.should_run() is False
    gate.note_session()
    gate.note_session()
    assert gate.should_run() is True
    assert gate.try_acquire() is True
    gate.mark_success()
    assert gate.should_run() is False


def test_lock_blocks_live_pid(tmp_path: Path) -> None:
    gate = DreamGate(tmp_path, min_hours=0, min_sessions=0)
    gate.try_acquire()
    other = DreamGate(tmp_path, min_hours=0, min_sessions=0)
    assert other.try_acquire() is False

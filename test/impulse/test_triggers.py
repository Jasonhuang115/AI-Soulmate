from datetime import date, datetime

from asm.impulse.triggers import due_callbacks, idle_companion, session_open


def test_session_open_delta() -> None:
    now = datetime(2026, 9, 14, 12, 0)
    last = datetime(2026, 9, 14, 9, 0)
    trigger = session_open(last, now)
    assert trigger.reason == "session_open"
    assert "3 小时" in trigger.hint


def test_due_callbacks() -> None:
    text = "截止日期: 2026-09-01 问面试\n截止日期: 2026-12-01 以后再说"
    items = due_callbacks(text, date(2026, 9, 14))
    assert len(items) == 1
    assert "2026-09-01" in items[0].hint


def test_idle_companion_respects_gates() -> None:
    assert idle_companion(10, True, 180, "有点委屈") is None
    assert idle_companion(200, False, 180, "有点委屈") is None
    assert idle_companion(200, True, 180, "  ") is None
    hit = idle_companion(200, True, 180, "有点委屈，他刚才那句话")
    assert hit is not None
    assert hit.reason == "idle_companion"
    assert hit.hint == "有点委屈，他刚才那句话"

from datetime import datetime
from pathlib import Path

from asm.emotion.now import NowStore, parse_self_state_text, render_self_state


def test_roundtrip_file(tmp_path: Path) -> None:
    path = tmp_path / "self_state.md"
    store = NowStore(path)
    at = datetime(2026, 9, 17, 19, 41, 0)
    store.commit("有点委屈，他刚才那句话", "t1", at)
    text = path.read_text(encoding="utf-8")
    assert parse_self_state_text(text) == store.mood
    loaded = NowStore(path)
    assert loaded.mood is not None
    assert loaded.mood.text == "有点委屈，他刚才那句话"
    assert loaded.mood.source_turn == "t1"


def test_commit_from_raw_keeps_last(tmp_path: Path) -> None:
    store = NowStore(tmp_path / "self_state.md")
    store.commit_from_raw("先⟦此刻 有点闷⟧。⟦happy⟧⟦此刻 被那句话刺到⟧", "t2", datetime(2026, 9, 17, 12, 0))
    assert store.mood is not None
    assert store.mood.text == "被那句话刺到"
    store.commit_from_raw("没有标记", "t3", datetime(2026, 9, 17, 12, 1))
    assert store.mood.text == "被那句话刺到"


def test_expire_cross_day_and_reunion_clear(tmp_path: Path) -> None:
    store = NowStore(tmp_path / "self_state.md")
    store.commit("有点委屈", "t1", datetime(2026, 9, 17, 23, 50))
    store.expire_if_stale(datetime(2026, 9, 18, 0, 1))
    assert store.mood is None
    assert store.live_body() == ""

    store.commit("有点委屈", "t1", datetime(2026, 9, 17, 19, 0))
    store.after_successful_turn()
    store.mark_reunion(datetime(2026, 9, 17, 21, 0))
    assert store.reunion
    kwargs = store.situation_kwargs(datetime(2026, 9, 17, 21, 0))
    assert kwargs["reunion"] is True
    store.after_successful_turn()
    assert store.mood is None
    assert store.reunion is False


def test_reunion_keeps_new_now(tmp_path: Path) -> None:
    store = NowStore(tmp_path / "self_state.md")
    store.commit("有点委屈", "t1", datetime(2026, 9, 17, 19, 0))
    store.mark_reunion(datetime(2026, 9, 17, 21, 0))
    store.commit_from_raw("⟦此刻 已经没事了⟧", "t2", datetime(2026, 9, 17, 21, 1))
    store.after_successful_turn()
    assert store.mood is not None
    assert store.mood.text == "已经没事了"
    assert store.reunion is False


def test_render_has_no_scale_words() -> None:
    mood = parse_self_state_text(
        render_self_state(
            parse_self_state_text(
                "此刻：有点委屈\n写下：2026-09-17T19:41:00\n来源：t1\n"
            )
        )
    )
    assert mood is not None
    assert "valence" not in mood.text

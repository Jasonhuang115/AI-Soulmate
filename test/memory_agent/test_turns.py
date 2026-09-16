from pathlib import Path

from memory_agent.store.turns import TurnStore, escape_like


def _store(tmp_path: Path) -> TurnStore:
    return TurnStore(tmp_path / "turns.sqlite", jsonl_dir=tmp_path / "missing")


def _add(store: TurnStore, i: int, user: str, assistant: str = "嗯", ts: str | None = None) -> None:
    store.append(f"t{i}", user, assistant, ts=ts or f"2026-09-15T12:{i:02d}:00")


def test_recent_default_is_newest_first(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _add(store, 1, "早")
    _add(store, 2, "红茶")
    _add(store, 3, "周五")
    result = store.search(n=2)
    assert [item["user"] for item in result["turns"]] == ["周五", "红茶"]
    assert result["truncated"] is True
    assert store.search(n=3)["truncated"] is False


def test_since_until_and_day(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append("a", "昨天", "好", ts="2026-09-14T23:59:00")
    store.append("b", "早上", "好", ts="2026-09-15T09:00:00")
    store.append("c", "晚上", "好", ts="2026-09-15T20:00:00")
    store.append("d", "明天", "好", ts="2026-09-16T00:00:00")
    day = store.search(day="2026-09-15", order="asc")
    assert [item["user"] for item in day["turns"]] == ["早上", "晚上"]
    window = store.search(since="2026-09-15T10:00:00", until="2026-09-16T00:00:00", order="asc")
    assert [item["user"] for item in window["turns"]] == ["晚上"]
    inclusive = store.search(
        since="2026-09-15T09:00:00", until="2026-09-15T09:00:01", order="asc"
    )
    assert [item["user"] for item in inclusive["turns"]] == ["早上"]


def test_pattern_field_and_like_escape(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append("a", "100% 果汁", "好", ts="2026-09-15T12:00:00")
    store.append("b", "普通果汁", "含_符号", ts="2026-09-15T12:01:00")
    store.append("c", "红茶", "记下了", ts="2026-09-15T12:02:00")
    store.append("d", "I drink Tea", "ok", ts="2026-09-15T12:03:00")
    percent = store.search(pattern="%", order="asc")
    assert [item["user"] for item in percent["turns"]] == ["100% 果汁"]
    unders = store.search(pattern="_", order="asc")
    assert [item["user"] for item in unders["turns"]] == ["普通果汁"]
    users = store.search(pattern="果汁", field="user", order="asc")
    assert [item["user"] for item in users["turns"]] == ["100% 果汁", "普通果汁"]
    assistants = store.search(pattern="记下了", field="assistant")
    assert [item["user"] for item in assistants["turns"]] == ["红茶"]
    assert [item["user"] for item in store.search(pattern="tea")["turns"]] == ["I drink Tea"]
    assert escape_like("%_") == "\\%\\_"


def test_n_capped_at_max(tmp_path: Path) -> None:
    from memory_agent.store.turns import MAX_N

    store = _store(tmp_path)
    for i in range(6):
        _add(store, i, f"话{i}")
    result = store.search(n=1000, order="asc")
    assert len(result["turns"]) == 6
    assert result["truncated"] is False
    assert MAX_N == 500


def test_truncated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(6):
        _add(store, i, f"话{i}")
    result = store.search(n=5, order="asc")
    assert len(result["turns"]) == 5
    assert result["truncated"] is True


def test_import_jsonl_when_empty(tmp_path: Path) -> None:
    folder = tmp_path / "transcripts"
    folder.mkdir()
    (folder / "2026-09-15.jsonl").write_text(
        '{"ts":"2026-09-15T17:48:00","turn_id":"t","user":"我每天喝红茶","assistant":"好","interrupted":false}\n',
        encoding="utf-8",
    )
    store = TurnStore(tmp_path / "turns.sqlite")
    assert store.count() == 1
    assert store.search(pattern="红茶")["turns"][0]["user"] == "我每天喝红茶"
    again = TurnStore(tmp_path / "turns.sqlite")
    assert again.count() == 1


def test_day_intersects_since(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append("a", "早", "好", ts="2026-09-15T08:00:00")
    store.append("b", "午", "好", ts="2026-09-15T13:00:00")
    result = store.search(day="2026-09-15", since="2026-09-15T10:00:00", order="asc")
    assert [item["user"] for item in result["turns"]] == ["午"]


def test_count_since(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append("a", "早", "好", ts="2026-09-15T08:00:00")
    store.append("b", "午", "好", ts="2026-09-15T13:00:00")
    assert store.count() == 2
    assert store.count(since="2026-09-15T10:00:00") == 1
    assert store.count(since="2026-09-15T13:00:00", exclusive=True) == 0
    assert store.count(since="2026-09-16T00:00:00") == 0

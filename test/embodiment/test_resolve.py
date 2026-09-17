from embodiment.resolve import classify, log_unresolved


def test_classify_emotions_motions_and_stop() -> None:
    assert classify("happy") == ("emotion", "happy")
    assert classify("wave") == ("motion", "wave")
    assert classify("Wave_Hand") == ("motion", "wave")
    assert classify("stop") == ("control", "stop")
    assert classify("dance") == ("motion", "dance")
    assert classify("not_a_clip") is None


def test_log_unresolved(tmp_path) -> None:
    dest = tmp_path / "unresolved_markers.jsonl"
    log_unresolved("nope", dest)
    log_unresolved("nope", dest)
    lines = dest.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert "nope" in lines[0]

from embodiment.catalog import (
    catalog_path,
    gesture_names,
    load_catalog,
    motion_groups,
    prompt_motion_names,
    prompt_phase,
    scan_vrma_stems,
)
from embodiment.vocab import EMOTIONS, MOTIONS, PROMPT_MOTIONS


def test_catalog_phase_counts() -> None:
    catalog = load_catalog()
    gestures = catalog["gestures"]
    phase1 = [name for name, spec in gestures.items() if int(spec.get("phase") or 1) == 1]
    upto2 = [name for name, spec in gestures.items() if int(spec.get("phase") or 1) <= 2]
    upto3 = [name for name, spec in gestures.items() if int(spec.get("phase") or 1) <= 3]
    assert 12 <= len(phase1) <= 15
    assert len(upto2) == 50
    assert len(upto3) >= 100
    assert set(phase1).isdisjoint(EMOTIONS)
    assert set(gestures).isdisjoint(EMOTIONS)


def test_vocab_matches_catalog() -> None:
    assert MOTIONS == gesture_names()
    assert PROMPT_MOTIONS == prompt_motion_names()
    assert prompt_phase() == 3
    assert set(PROMPT_MOTIONS) <= set(MOTIONS)
    assert len(PROMPT_MOTIONS) == 50
    for name in PROMPT_MOTIONS:
        spec = load_catalog()["gestures"][name]
        assert spec.get("prompt") is not False
        assert int(spec.get("phase") or 1) <= prompt_phase()


def test_phase1_clips_are_named() -> None:
    for name in PROMPT_MOTIONS:
        spec = load_catalog()["gestures"][name]
        assert spec.get("file", "").endswith(".vrma")


def test_later_phases_have_sources() -> None:
    for spec in load_catalog()["gestures"].values():
        if int(spec.get("phase") or 1) >= 2:
            assert spec.get("source") or spec.get("mixamo")


def test_motion_groups_cover_prompt() -> None:
    grouped = {name for names in motion_groups().values() for name in names}
    assert grouped == set(PROMPT_MOTIONS)


def test_scan_handles_missing_dir(tmp_path) -> None:
    assert scan_vrma_stems(tmp_path / "none") == set()


def test_phase3_prompt_stays_curated() -> None:
    gestures = load_catalog()["gestures"]
    promptable = [
        name
        for name, spec in gestures.items()
        if spec.get("prompt") is not False and int(spec.get("phase") or 1) <= 3
    ]
    assert len(promptable) == 50


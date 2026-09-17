from embodiment.catalog import (
    catalog_path,
    gesture_names,
    load_catalog,
    motion_groups,
    motion_kind,
    prompt_motion_names,
    scan_vrma_stems,
)
from embodiment.vocab import EMOTIONS, MOTIONS, PROMPT_MOTIONS


def test_catalog_phase_counts() -> None:
    catalog = load_catalog()
    gestures = catalog["gestures"]
    phase1 = [name for name, spec in gestures.items() if int(spec.get("phase") or 1) == 1]
    assert 12 <= len(phase1) <= 15
    assert len(gestures) >= 100
    assert set(phase1).isdisjoint(EMOTIONS)
    assert set(gestures).isdisjoint(EMOTIONS)


def test_vocab_matches_catalog() -> None:
    assert MOTIONS == gesture_names()
    assert PROMPT_MOTIONS == prompt_motion_names()
    assert set(PROMPT_MOTIONS) == set(MOTIONS)
    assert len(PROMPT_MOTIONS) >= 100
    for name in PROMPT_MOTIONS:
        spec = load_catalog()["gestures"][name]
        assert spec.get("file", "").endswith(".vrma")
        assert spec.get("kind") in {"gesture", "pose", "loop", "transition"}
        assert spec.get("desc") or spec.get("label")


def test_poses_have_holds() -> None:
    for name, spec in load_catalog()["gestures"].items():
        if spec.get("kind") == "pose":
            assert spec.get("holds")
            assert motion_kind(name) == "pose"


def test_later_phases_have_sources() -> None:
    for spec in load_catalog()["gestures"].values():
        if int(spec.get("phase") or 1) >= 2:
            assert spec.get("source") or spec.get("mixamo")


def test_motion_groups_cover_prompt() -> None:
    grouped = {name for names in motion_groups().values() for name in names}
    assert grouped == set(PROMPT_MOTIONS)


def test_scan_handles_missing_dir(tmp_path) -> None:
    assert scan_vrma_stems(tmp_path / "none") == set()
    assert catalog_path().name == "catalog.json"

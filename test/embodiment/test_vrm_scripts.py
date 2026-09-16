from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_asset_and_convert_scripts_exist() -> None:
    assert (ROOT / "scripts/fetch_vrm_assets.sh").is_file()
    assert (ROOT / "scripts/fetch_motion_packs.sh").is_file()
    assert (ROOT / "scripts/convert_mixamo_to_vrma.sh").is_file()
    assert (ROOT / "scripts/convert_gestures.py").is_file()
    assert (ROOT / "scripts/bvh_to_vrma.py").is_file()
    assert (ROOT / "scripts/sync_gesture_catalog.py").is_file()
    assert (ROOT / "frontend/public/gestures/NOTICE.txt").is_file()
    notice = (ROOT / "frontend/public/gestures/NOTICE.txt").read_text(encoding="utf-8")
    assert "Motifect" in notice
    assert "three-vrm" in notice

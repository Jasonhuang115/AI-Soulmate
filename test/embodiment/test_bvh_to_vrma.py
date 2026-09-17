from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from bvh_to_vrma import convert_bvh, inspect_vrma  # noqa: E402
from gesture_sources import GESTURE_SOURCES, assert_unique_sources  # noqa: E402


def _joint(name: str, channels: str, body: str) -> str:
    return f"JOINT {name}\n{{\n\tOFFSET 0.0 1.0 0.0\n\t{channels}\n{body}}}\n"


def _minimal_bvh(frames: int = 8, dt: float = 0.033333) -> str:
    # Enough Motifect-named bones to pass the humanoid floor.
    hand = _joint(
        "LeftHand",
        "CHANNELS 3 Zrotation Yrotation Xrotation",
        "",
    )
    forearm = _joint(
        "LeftForeArm",
        "CHANNELS 3 Zrotation Yrotation Xrotation",
        hand,
    )
    arm = _joint(
        "LeftArm",
        "CHANNELS 3 Zrotation Yrotation Xrotation",
        forearm,
    )
    l_shoulder = _joint(
        "LeftShoulder",
        "CHANNELS 3 Zrotation Yrotation Xrotation",
        arm,
    )
    r_hand = _joint(
        "RightHand",
        "CHANNELS 3 Zrotation Yrotation Xrotation",
        "",
    )
    r_fore = _joint(
        "RightForeArm",
        "CHANNELS 3 Zrotation Yrotation Xrotation",
        r_hand,
    )
    r_arm = _joint(
        "RightArm",
        "CHANNELS 3 Zrotation Yrotation Xrotation",
        r_fore,
    )
    r_shoulder = _joint(
        "RightShoulder",
        "CHANNELS 3 Zrotation Yrotation Xrotation",
        r_arm,
    )
    head = _joint("Head", "CHANNELS 3 Zrotation Yrotation Xrotation", "")
    neck = _joint("Neck1", "CHANNELS 3 Zrotation Yrotation Xrotation", head)
    chest = _joint(
        "Chest",
        "CHANNELS 3 Zrotation Yrotation Xrotation",
        neck + l_shoulder + r_shoulder,
    )
    spine2 = _joint("Spine2", "CHANNELS 3 Zrotation Yrotation Xrotation", chest)
    spine1 = _joint("Spine1", "CHANNELS 3 Zrotation Yrotation Xrotation", spine2)
    shin = _joint("LeftShin", "CHANNELS 3 Zrotation Yrotation Xrotation", "")
    leg = _joint("LeftLeg", "CHANNELS 3 Zrotation Yrotation Xrotation", shin)
    zeros = " ".join(["0"] * (6 + 3 * 15))
    motion = "\n".join([zeros] * frames)
    return (
        "HIERARCHY\n"
        "ROOT Hips\n{\n"
        "\tOFFSET 0.0 0.0 0.0\n"
        "\tCHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation\n"
        f"{spine1}{leg}}}\n"
        "MOTION\n"
        f"Frames: {frames}\n"
        f"Frame Time: {dt}\n"
        f"{motion}\n"
    )


def test_gesture_sources_are_unique() -> None:
    assert_unique_sources()
    assert len(GESTURE_SOURCES) == 88


def test_bvh_converts_to_vrma(tmp_path: Path) -> None:
    dest = tmp_path / "nod.vrma"
    info = convert_bvh(_minimal_bvh(), dest)
    assert dest.is_file()
    assert info["bones"] >= 15
    assert info["duration"] > 0.2
    inspected = inspect_vrma(dest)
    assert inspected["bones"] == info["bones"]
    assert inspected["size"] > 100

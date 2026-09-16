#!/usr/bin/env python3
"""Convert a Motifect-style Mixamo-named BVH clip to a VRM 1.0 .vrma (GLB)."""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCALE = 0.01  # Motifect BVH is authored in centimetres.

# Motifect / Mixamo-style joint name -> VRM 1.0 humanoid bone.
HUMANOID: dict[str, str] = {
    "Hips": "hips",
    "Spine1": "spine",
    "Spine2": "chest",
    "Chest": "upperChest",
    "Neck1": "neck",
    "Head": "head",
    "LeftShoulder": "leftShoulder",
    "LeftArm": "leftUpperArm",
    "LeftForeArm": "leftLowerArm",
    "LeftHand": "leftHand",
    "RightShoulder": "rightShoulder",
    "RightArm": "rightUpperArm",
    "RightForeArm": "rightLowerArm",
    "RightHand": "rightHand",
    "LeftLeg": "leftUpperLeg",
    "LeftShin": "leftLowerLeg",
    "LeftFoot": "leftFoot",
    "LeftToeBase": "leftToes",
    "RightLeg": "rightUpperLeg",
    "RightShin": "rightLowerLeg",
    "RightFoot": "rightFoot",
    "RightToeBase": "rightToes",
    "LeftHandThumb1": "leftThumbMetacarpal",
    "LeftHandThumb2": "leftThumbProximal",
    "LeftHandThumb3": "leftThumbDistal",
    "LeftHandIndex1": "leftIndexProximal",
    "LeftHandIndex2": "leftIndexIntermediate",
    "LeftHandIndex3": "leftIndexDistal",
    "LeftHandMiddle1": "leftMiddleProximal",
    "LeftHandMiddle2": "leftMiddleIntermediate",
    "LeftHandMiddle3": "leftMiddleDistal",
    "LeftHandRing1": "leftRingProximal",
    "LeftHandRing2": "leftRingIntermediate",
    "LeftHandRing3": "leftRingDistal",
    "LeftHandPinky1": "leftLittleProximal",
    "LeftHandPinky2": "leftLittleIntermediate",
    "LeftHandPinky3": "leftLittleDistal",
    "RightHandThumb1": "rightThumbMetacarpal",
    "RightHandThumb2": "rightThumbProximal",
    "RightHandThumb3": "rightThumbDistal",
    "RightHandIndex1": "rightIndexProximal",
    "RightHandIndex2": "rightIndexIntermediate",
    "RightHandIndex3": "rightIndexDistal",
    "RightHandMiddle1": "rightMiddleProximal",
    "RightHandMiddle2": "rightMiddleIntermediate",
    "RightHandMiddle3": "rightMiddleDistal",
    "RightHandRing1": "rightRingProximal",
    "RightHandRing2": "rightRingIntermediate",
    "RightHandRing3": "rightRingDistal",
    "RightHandPinky1": "rightLittleProximal",
    "RightHandPinky2": "rightLittleIntermediate",
    "RightHandPinky3": "rightLittleDistal",
}

NODE_NAMES = {
    "hips": "Hips",
    "spine": "Spine",
    "chest": "Chest",
    "upperChest": "UpperChest",
    "neck": "Neck",
    "head": "Head",
    "leftShoulder": "LeftShoulder",
    "leftUpperArm": "LeftUpperArm",
    "leftLowerArm": "LeftLowerArm",
    "leftHand": "LeftHand",
    "rightShoulder": "RightShoulder",
    "rightUpperArm": "RightUpperArm",
    "rightLowerArm": "RightLowerArm",
    "rightHand": "RightHand",
    "leftUpperLeg": "LeftUpperLeg",
    "leftLowerLeg": "LeftLowerLeg",
    "leftFoot": "LeftFoot",
    "leftToes": "LeftToes",
    "rightUpperLeg": "RightUpperLeg",
    "rightLowerLeg": "RightLowerLeg",
    "rightFoot": "RightFoot",
    "rightToes": "RightToes",
    "leftThumbMetacarpal": "LeftThumbMetacarpal",
    "leftThumbProximal": "LeftThumbProximal",
    "leftThumbDistal": "LeftThumbDistal",
    "leftIndexProximal": "LeftIndexProximal",
    "leftIndexIntermediate": "LeftIndexIntermediate",
    "leftIndexDistal": "LeftIndexDistal",
    "leftMiddleProximal": "LeftMiddleProximal",
    "leftMiddleIntermediate": "LeftMiddleIntermediate",
    "leftMiddleDistal": "LeftMiddleDistal",
    "leftRingProximal": "LeftRingProximal",
    "leftRingIntermediate": "LeftRingIntermediate",
    "leftRingDistal": "LeftRingDistal",
    "leftLittleProximal": "LeftLittleProximal",
    "leftLittleIntermediate": "LeftLittleIntermediate",
    "leftLittleDistal": "LeftLittleDistal",
    "rightThumbMetacarpal": "RightThumbMetacarpal",
    "rightThumbProximal": "RightThumbProximal",
    "rightThumbDistal": "RightThumbDistal",
    "rightIndexProximal": "RightIndexProximal",
    "rightIndexIntermediate": "RightIndexIntermediate",
    "rightIndexDistal": "RightIndexDistal",
    "rightMiddleProximal": "RightMiddleProximal",
    "rightMiddleIntermediate": "RightMiddleIntermediate",
    "rightMiddleDistal": "RightMiddleDistal",
    "rightRingProximal": "RightRingProximal",
    "rightRingIntermediate": "RightRingIntermediate",
    "rightRingDistal": "RightRingDistal",
    "rightLittleProximal": "RightLittleProximal",
    "rightLittleIntermediate": "RightLittleIntermediate",
    "rightLittleDistal": "RightLittleDistal",
}


@dataclass
class Joint:
    name: str
    offset: tuple[float, float, float]
    channels: list[str]
    parent: str | None
    children: list[str] = field(default_factory=list)
    channel_offset: int = 0


def _tokens(text: str) -> list[str]:
    return re.findall(r"[{}]|[^\s{}]+", text)


def parse_bvh(text: str) -> tuple[dict[str, Joint], list[list[float]], float]:
    motion_at = text.find("MOTION")
    if motion_at < 0:
        raise ValueError("BVH missing MOTION section")
    hierarchy = text[:motion_at]
    motion = text[motion_at:]
    tokens = _tokens(hierarchy)
    joints: dict[str, Joint] = {}
    channel_cursor = 0

    def parse_joint(index: int, parent: str | None) -> int:
        nonlocal channel_cursor
        kind = tokens[index]
        if kind not in {"ROOT", "JOINT"}:
            raise ValueError(f"expected ROOT/JOINT, got {kind}")
        name = tokens[index + 1]
        if tokens[index + 2] != "{":
            raise ValueError(f"joint {name} missing '{{'")
        index += 3
        offset = (0.0, 0.0, 0.0)
        channels: list[str] = []
        children: list[str] = []
        this_channel_offset = channel_cursor
        while tokens[index] != "}":
            item = tokens[index]
            if item == "OFFSET":
                offset = (
                    float(tokens[index + 1]),
                    float(tokens[index + 2]),
                    float(tokens[index + 3]),
                )
                index += 4
            elif item == "CHANNELS":
                count = int(tokens[index + 1])
                channels = tokens[index + 2 : index + 2 + count]
                this_channel_offset = channel_cursor
                channel_cursor += count
                index += 2 + count
            elif item in {"ROOT", "JOINT"}:
                child_name = tokens[index + 1]
                children.append(child_name)
                index = parse_joint(index, name)
            elif item == "End":
                # End Site { OFFSET x y z }
                while tokens[index] != "}":
                    index += 1
                index += 1
            else:
                raise ValueError(f"unexpected token in joint {name}: {item}")
        joint = Joint(
            name=name,
            offset=offset,
            channels=channels,
            parent=parent,
            children=children,
            channel_offset=this_channel_offset,
        )
        joints[name] = joint
        return index + 1

    index = 0
    if tokens[index] == "HIERARCHY":
        index += 1
    parse_joint(index, None)

    frames_match = re.search(r"Frames:\s*(\d+)", motion)
    time_match = re.search(r"Frame Time:\s*([0-9.eE+-]+)", motion)
    if not frames_match or not time_match:
        raise ValueError("BVH missing Frames / Frame Time")
    n_frames = int(frames_match.group(1))
    dt = float(time_match.group(1))
    rest = motion[time_match.end() :].strip()
    rows: list[list[float]] = []
    for line in rest.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append([float(part) for part in line.split()])
    if len(rows) != n_frames:
        raise ValueError(f"expected {n_frames} frames, got {len(rows)}")
    if rows and len(rows[0]) != channel_cursor:
        raise ValueError(f"expected {channel_cursor} channels, got {len(rows[0])}")
    return joints, rows, dt


def _quat_mul(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _quat_axis_angle(axis: tuple[float, float, float], degrees: float) -> tuple[float, float, float, float]:
    half = math.radians(degrees) * 0.5
    s = math.sin(half)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(half))


def euler_zyx(z: float, y: float, x: float) -> tuple[float, float, float, float]:
    """BVH CHANNELS Zrotation Yrotation Xrotation → glTF xyzw quaternion."""
    qx = _quat_axis_angle((1.0, 0.0, 0.0), x)
    qy = _quat_axis_angle((0.0, 1.0, 0.0), y)
    qz = _quat_axis_angle((0.0, 0.0, 1.0), z)
    return _quat_mul(qz, _quat_mul(qy, qx))


def _flip_hemisphere(
    prev: tuple[float, float, float, float],
    quat: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if prev[0] * quat[0] + prev[1] * quat[1] + prev[2] * quat[2] + prev[3] * quat[3] < 0:
        return (-quat[0], -quat[1], -quat[2], -quat[3])
    return quat


def _add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mapped_parent(joints: dict[str, Joint], name: str) -> str | None:
    parent = joints[name].parent
    while parent is not None:
        if parent in HUMANOID:
            return parent
        parent = joints[parent].parent
    return None


def _rest_offset(joints: dict[str, Joint], name: str) -> tuple[float, float, float]:
    acc = joints[name].offset
    parent = joints[name].parent
    while parent is not None and parent not in HUMANOID:
        acc = _add(joints[parent].offset, acc)
        parent = joints[parent].parent
    return (acc[0] * SCALE, acc[1] * SCALE, acc[2] * SCALE)


def _sample_rotation(joint: Joint, row: list[float]) -> tuple[float, float, float, float]:
    values = {channel: row[joint.channel_offset + i] for i, channel in enumerate(joint.channels)}
    return euler_zyx(
        values.get("Zrotation", 0.0),
        values.get("Yrotation", 0.0),
        values.get("Xrotation", 0.0),
    )


def _sample_translation(joint: Joint, row: list[float]) -> tuple[float, float, float]:
    values = {channel: row[joint.channel_offset + i] for i, channel in enumerate(joint.channels)}
    return (
        values.get("Xposition", 0.0),
        values.get("Yposition", 0.0),
        values.get("Zposition", 0.0),
    )


def _align4(length: int) -> int:
    return (4 - (length % 4)) % 4


def _write_glb(gltf: dict[str, Any], blob: bytes, dest: Path) -> None:
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_pad = _align4(len(json_bytes))
    json_chunk = json_bytes + (b" " * json_pad)
    bin_pad = _align4(len(blob))
    bin_chunk = blob + (b"\x00" * bin_pad)
    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    header = struct.pack("<III", 0x46546C67, 2, total)
    json_header = struct.pack("<II", len(json_chunk), 0x4E4F534A)
    bin_header = struct.pack("<II", len(bin_chunk), 0x004E4942)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(header + json_header + json_chunk + bin_header + bin_chunk)


def convert_bvh(text: str, dest: Path, *, in_place: bool = True) -> dict[str, Any]:
    joints, rows, dt = parse_bvh(text)
    mapped = [name for name in joints if name in HUMANOID]
    if "Hips" not in mapped:
        raise ValueError("BVH has no Hips joint")
    if len(mapped) < 15:
        raise ValueError(f"too few humanoid bones: {len(mapped)}")

    children: dict[str, list[str]] = {name: [] for name in mapped}
    roots: list[str] = []
    for name in mapped:
        parent = _mapped_parent(joints, name)
        if parent is None:
            roots.append(name)
        else:
            children[parent].append(name)
    if roots != ["Hips"]:
        raise ValueError(f"expected single Hips root, got {roots}")

    ordered: list[str] = []

    def walk(name: str) -> None:
        ordered.append(name)
        for child in children[name]:
            walk(child)

    walk("Hips")
    index_of = {name: i for i, name in enumerate(ordered)}

    nodes: list[dict[str, Any]] = []
    for name in ordered:
        vrm = HUMANOID[name]
        node: dict[str, Any] = {
            "name": NODE_NAMES[vrm],
            "translation": list(_rest_offset(joints, name)),
        }
        child_ids = [index_of[child] for child in children[name]]
        if child_ids:
            node["children"] = child_ids
        nodes.append(node)

    n_frames = len(rows)
    times = [i * dt for i in range(n_frames)]
    duration = times[-1] if times else 0.0
    if duration < 0.2:
        raise ValueError(f"clip too short: {duration:.3f}s")

    hips = joints["Hips"]
    origin = _sample_translation(hips, rows[0]) if rows else (0.0, 0.0, 0.0)
    translations: list[tuple[float, float, float]] = []
    for row in rows:
        pos = _sample_translation(hips, row)
        if in_place:
            translations.append(
                (
                    (pos[0] - origin[0]) * SCALE,
                    pos[1] * SCALE,
                    (pos[2] - origin[2]) * SCALE,
                )
            )
        else:
            translations.append((pos[0] * SCALE, pos[1] * SCALE, pos[2] * SCALE))
    if translations:
        nodes[index_of["Hips"]]["translation"] = list(translations[0])

    rotations: dict[str, list[tuple[float, float, float, float]]] = {}
    for name in ordered:
        series: list[tuple[float, float, float, float]] = []
        prev = (0.0, 0.0, 0.0, 1.0)
        for row in rows:
            quat = _sample_rotation(joints[name], row)
            quat = _flip_hemisphere(prev, quat)
            series.append(quat)
            prev = quat
        rotations[name] = series

    blob = bytearray()
    buffer_views: list[dict[str, int]] = []
    accessors: list[dict[str, Any]] = []

    def add_accessor(data: bytes, accessor: dict[str, Any]) -> int:
        pad = _align4(len(blob))
        if pad:
            blob.extend(b"\x00" * pad)
        view_index = len(buffer_views)
        buffer_views.append(
            {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        )
        blob.extend(data)
        accessor["bufferView"] = view_index
        accessors.append(accessor)
        return len(accessors) - 1

    time_bytes = struct.pack("<" + "f" * n_frames, *times)
    time_accessor = add_accessor(
        time_bytes,
        {
            "componentType": 5126,
            "count": n_frames,
            "type": "SCALAR",
            "min": [times[0]],
            "max": [times[-1]],
        },
    )

    channels: list[dict[str, Any]] = []
    samplers: list[dict[str, Any]] = []

    hip_data = struct.pack("<" + "f" * (n_frames * 3), *[v for t in translations for v in t])
    hip_accessor = add_accessor(
        hip_data,
        {"componentType": 5126, "count": n_frames, "type": "VEC3"},
    )
    samplers.append({"input": time_accessor, "interpolation": "LINEAR", "output": hip_accessor})
    channels.append({"sampler": 0, "target": {"node": index_of["Hips"], "path": "translation"}})

    for name in ordered:
        series = rotations[name]
        rot_bytes = struct.pack("<" + "f" * (n_frames * 4), *[v for q in series for v in q])
        rot_accessor = add_accessor(
            rot_bytes,
            {"componentType": 5126, "count": n_frames, "type": "VEC4"},
        )
        sampler_index = len(samplers)
        samplers.append(
            {"input": time_accessor, "interpolation": "LINEAR", "output": rot_accessor}
        )
        channels.append(
            {
                "sampler": sampler_index,
                "target": {"node": index_of[name], "path": "rotation"},
            }
        )

    human_bones = {HUMANOID[name]: {"node": index_of[name]} for name in ordered}
    gltf = {
        "asset": {"version": "2.0", "generator": "asm-bvh-to-vrma"},
        "scene": 0,
        "scenes": [{"nodes": [index_of["Hips"]]}],
        "nodes": nodes,
        "animations": [{"name": dest.stem, "channels": channels, "samplers": samplers}],
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(blob)}],
        "extensionsUsed": ["VRMC_vrm_animation"],
        "extensions": {
            "VRMC_vrm_animation": {
                "specVersion": "1.0",
                "humanoid": {"humanBones": human_bones},
            }
        },
    }
    _write_glb(gltf, bytes(blob), dest)
    return {
        "bones": len(human_bones),
        "frames": n_frames,
        "duration": duration,
        "path": str(dest),
    }


def convert_file(src: Path, dest: Path, *, in_place: bool = True) -> dict[str, Any]:
    return convert_bvh(src.read_text(encoding="utf-8", errors="ignore"), dest, in_place=in_place)


def inspect_vrma(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise ValueError(f"{path.name} is not GLB")
    chunk_len, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != 0x4E4F534A:
        raise ValueError(f"{path.name} missing JSON chunk")
    gltf = json.loads(data[20 : 20 + chunk_len])
    bones = (
        (gltf.get("extensions") or {})
        .get("VRMC_vrm_animation", {})
        .get("humanoid", {})
        .get("humanBones")
        or {}
    )
    accessors = gltf.get("accessors") or []
    duration = 0.0
    for accessor in accessors:
        if accessor.get("type") == "SCALAR" and accessor.get("max"):
            duration = max(duration, float(accessor["max"][0]))
    return {
        "bones": len(bones),
        "duration": duration,
        "nodes": len(gltf.get("nodes") or []),
        "size": path.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--keep-root-motion", action="store_true")
    args = parser.parse_args()
    dest = args.output or args.input.with_suffix(".vrma")
    info = convert_file(args.input, dest, in_place=not args.keep_root_motion)
    print(
        f"{dest}  bones={info['bones']}  frames={info['frames']}  duration={info['duration']:.2f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

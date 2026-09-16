import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "frontend/public/models/epsilon/Epsilon2.1.model.json"
MAP = ROOT / "frontend/public/models/epsilon/avatar_map.json"


def test_epsilon_expression_names_exist_on_model() -> None:
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    mapping = json.loads(MAP.read_text(encoding="utf-8"))
    names = {item["name"] for item in model["expressions"]}
    files = {item["file"].rsplit("/", 1)[-1] for item in model["expressions"]}
    for logic, mapped in mapping["expressions"].items():
        assert mapped in names or mapped in files, logic
        assert logic in mapping["expression_params"]


def test_epsilon_motion_indices_exist() -> None:
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    mapping = json.loads(MAP.read_text(encoding="utf-8"))
    groups = model["motions"]
    for name, spec in mapping["motions"].items():
        group = spec["group"]
        index = spec["index"]
        assert group in groups, name
        assert 0 <= index < len(groups[group]), name
    idle = mapping["idle"]
    assert idle["group"] in groups
    assert 0 <= idle["index"] < len(groups[idle["group"]])
    wave = groups[mapping["motions"]["wave"]["group"]][mapping["motions"]["wave"]["index"]]
    wave_path = ROOT / "frontend/public/models/epsilon" / wave["file"]
    assert "PARAM_ARM_L" in wave_path.read_text(encoding="utf-8")

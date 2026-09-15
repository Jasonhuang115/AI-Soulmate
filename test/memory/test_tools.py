from pathlib import Path

import pytest

from memory.paths import resolve_under
from memory.tools import MemoryTools, MEMORY_MAX_LINES


def test_escape_rejected(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    with pytest.raises(ValueError):
        resolve_under(tmp_path, "../secret")
    with pytest.raises(ValueError):
        tools.read("/etc/passwd")


def test_write_section_replaces_only_target(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    (tmp_path / "relationship.md").write_text("## A\nold-a\n## B\nold-b\n", encoding="utf-8")
    tools.write_section("relationship.md", "A", "new-a")
    text = tools.read("relationship.md")
    assert "new-a" in text
    assert "old-b" in text
    assert "old-a" not in text
    assert (tmp_path / ".changelog.jsonl").exists()


def test_persona_is_read_only(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    (tmp_path / "persona.md").write_text("阿澄\n", encoding="utf-8")
    with pytest.raises(PermissionError):
        tools.write("persona.md", "改名")
    with pytest.raises(PermissionError):
        tools.write_section("persona.md", "名", "改")
    assert tools.read("persona.md") == "阿澄\n"


def test_memory_md_cap_rejected(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    too_long = "\n".join(f"- line {i}" for i in range(MEMORY_MAX_LINES + 1))
    with pytest.raises(ValueError, match="lines"):
        tools.write("MEMORY.md", too_long)
    assert tools.read("MEMORY.md") == ""


def test_write_user_topic_allowed(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    tools.write("user/taste.md", "他喜欢红茶")
    assert "红茶" in tools.read("user/taste.md")

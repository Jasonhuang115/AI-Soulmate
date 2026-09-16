from pathlib import Path

import pytest

from memory_agent.store.paths import resolve_under
from memory_agent.store.tools import MemoryTools, MEMORY_MAX_LINES


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


def test_persona_cannot_be_written(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    (tmp_path / "persona.md").write_text("影子\n", encoding="utf-8")
    with pytest.raises(PermissionError):
        tools.write("persona.md", "改名")
    with pytest.raises(PermissionError):
        tools.write_section("persona.md", "名", "改")
    assert tools.read("persona.md") == ""
    assert "persona.md" not in tools.ls(".")


def test_memory_md_cap_rejected(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    too_long = "\n".join(f"- line {i}" for i in range(MEMORY_MAX_LINES + 1))
    with pytest.raises(ValueError, match="lines"):
        tools.write("MEMORY.md", too_long)
    assert tools.read("MEMORY.md") == ""


def test_write_user_md_allowed(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    tools.write("user.md", "他喜欢红茶")
    assert "红茶" in tools.read("user.md")
    with pytest.raises(PermissionError):
        tools.write("user/taste.md", "他喜欢红茶")


def test_ls_and_read_skip_self_state(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    (tmp_path / "self_state.md").write_text("心情\n", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("工作集\n", encoding="utf-8")
    names = tools.ls(".")
    assert "MEMORY.md" in names
    assert "self_state.md" not in names
    assert tools.read("self_state.md") == ""
    with pytest.raises(PermissionError):
        tools.write("self_state.md", "nope")


def test_ls_and_read_skip_sqlite(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    (tmp_path / "turns.sqlite").write_bytes(b"not a db")
    (tmp_path / "note.md").write_text("可见\n", encoding="utf-8")
    names = tools.ls(".")
    assert "note.md" in names
    assert not any(name.endswith(".sqlite") or ".sqlite-" in name for name in names)
    assert tools.read("turns.sqlite") == ""
    with pytest.raises(PermissionError):
        tools.write("turns.sqlite", "nope")


def test_ls_and_read_skip_rolling(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    (tmp_path / "rolling.md").write_text("近期脉络\n", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("工作集\n", encoding="utf-8")
    names = tools.ls(".")
    assert "MEMORY.md" in names
    assert "rolling.md" not in names
    assert tools.read("rolling.md") == ""
    with pytest.raises(PermissionError):
        tools.write("rolling.md", "nope")

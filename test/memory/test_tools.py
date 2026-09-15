from pathlib import Path

import pytest

from memory.paths import resolve_under
from memory.tools import MemoryTools


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

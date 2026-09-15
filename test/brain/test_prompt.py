from datetime import datetime
from pathlib import Path

import pytest
from embodiment.vocab import EMOTIONS, MOTIONS
from asm.brain.prompt import (
    REQUIRED_SECTIONS,
    assemble_framework,
    build_messages,
    format_situation,
    load_prompt_fragments,
)
from asm.core.interfaces import Message, PromptContext


def test_fragments_load_in_order() -> None:
    fragments = load_prompt_fragments()
    assert [item.section_name for item in fragments] == list(REQUIRED_SECTIONS)


def test_framework_uses_xml_tags() -> None:
    prompt = assemble_framework()
    soul = prompt.index("<soul>")
    medium = prompt.index("<medium>")
    tools = prompt.index("<tools>")
    assert soul < medium < tools
    assert "</soul>" in prompt
    assert "阿澄" in prompt
    assert "⟦happy⟧" in prompt
    assert "[emo=" not in prompt
    assert "1 到 3 句" in prompt
    for emotion in EMOTIONS:
        assert f"⟦{emotion}⟧" in prompt
    for motion in MOTIONS:
        assert f"⟦{motion}⟧" in prompt
    assert "必须再带动作标记" in prompt


def test_missing_prompts_dir_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt_fragments(tmp_path / "missing")


def test_missing_section_fails(tmp_path: Path) -> None:
    (tmp_path / "01-soul.md").write_text("阿澄", encoding="utf-8")
    (tmp_path / "02-medium.md").write_text("口语", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        load_prompt_fragments(tmp_path)


def test_prompt_order_and_runtime_context() -> None:
    messages = build_messages(
        context=PromptContext(),
        session_summary="互称：澄澄",
        situation="现在是测试时间。",
        history=(Message(role="user", content="早"), Message(role="assistant", content="早。")),
        user_text="在吗",
    )
    assert messages[0].role == "system"
    assert messages[0].content.startswith("<soul>")
    assert messages[-1] == Message(role="user", content="在吗")
    assert messages[-2].content == "早。"
    assert any(item.content.startswith("情境：") for item in messages)
    assert any(item.content.startswith("近期脉络：") for item in messages)
    assert not any("本次会话摘要" in item.content for item in messages)


def test_prompt_injects_only_memory_md() -> None:
    messages = build_messages(
        context=PromptContext(
            index="他叫我澄澄",
            relationship="档案里的关系不应出现",
            self_state="心情档案不应出现",
            snippets=("秘密片段",),
        ),
        session_summary="",
        situation="现在是测试时间。",
        history=(),
        user_text="在吗",
    )
    blob = "\n".join(item.content for item in messages)
    assert "长期记忆：\n他叫我澄澄" in blob
    assert "档案里的关系不应出现" not in blob
    assert "心情档案不应出现" not in blob
    assert "秘密片段" not in blob
    assert "相关记忆" not in blob


def test_situation_uses_injected_now() -> None:
    now = datetime(2026, 9, 14, 12, 0)
    text = format_situation(now)
    assert "2026-09-14" in text
    assert "星期一" in text

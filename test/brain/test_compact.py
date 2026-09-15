from asm.brain.compact import (
    clip_summary,
    drop_prefix_count,
    estimate_tokens,
    fill_limit,
    heuristic_summary,
    prompt_tokens,
)
from asm.core.interfaces import Message, PromptContext


def test_fill_limit_reserves_fifteen_percent() -> None:
    assert fill_limit(1_000_000, 0.15) == 850_000


def test_estimate_tokens_is_half_chars() -> None:
    assert estimate_tokens("abcd") == 2
    assert estimate_tokens("") == 0


def test_drop_prefix_keeps_recent_when_over() -> None:
    context = PromptContext()
    messages = [Message(role="user", content="x" * 40) for _ in range(10)]
    dropped = drop_prefix_count(
        framework="",
        context=context,
        summary="",
        messages=messages,
        limit=50,
    )
    assert dropped >= 1
    assert dropped <= 8
    kept = messages[dropped:]
    assert prompt_tokens(framework="", context=context, summary="", messages=kept) <= 50


def test_drop_prefix_zero_when_under() -> None:
    messages = [Message(role="user", content="hi"), Message(role="assistant", content="嗯")]
    assert (
        drop_prefix_count(
            framework="",
            context=PromptContext(),
            summary="",
            messages=messages,
            limit=850_000,
        )
        == 0
    )


def test_clip_summary_strips_tag_and_caps() -> None:
    assert clip_summary("<summary>\n互称：澄澄\n</summary>") == "互称：澄澄"
    assert len(clip_summary("字" * 5000)) == 2000


def test_heuristic_keeps_previous() -> None:
    assert heuristic_summary("旧脉络", [Message(role="user", content="新")]) == "旧脉络"

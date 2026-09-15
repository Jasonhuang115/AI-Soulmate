from __future__ import annotations

from asm.core.interfaces import Message, PromptContext

MAX_SUMMARY_CHARS = 2000


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(len(text) // 2, 1)


def fill_limit(window_tokens: int, reserve_ratio: float) -> int:
    ratio = min(max(reserve_ratio, 0.0), 0.9)
    return max(int(window_tokens * (1.0 - ratio)), 1)


def resident_text(context: PromptContext) -> str:
    return "\n\n".join(
        block
        for block in (context.index, context.relationship, context.self_state)
        if block.strip()
    )


def prompt_tokens(
    *,
    framework: str,
    context: PromptContext,
    summary: str,
    messages: list[Message] | tuple[Message, ...],
    user_text: str = "",
) -> int:
    total = estimate_tokens(framework)
    total += estimate_tokens(resident_text(context))
    total += estimate_tokens(summary)
    total += sum(estimate_tokens(item.content) for item in messages)
    total += estimate_tokens(user_text)
    return total


def drop_prefix_count(
    *,
    framework: str,
    context: PromptContext,
    summary: str,
    messages: list[Message] | tuple[Message, ...],
    limit: int,
    user_text: str = "",
    keep_min: int = 2,
) -> int:
    msgs = list(messages)
    if not msgs:
        return 0
    if prompt_tokens(
        framework=framework,
        context=context,
        summary=summary,
        messages=msgs,
        user_text=user_text,
    ) <= limit:
        return 0
    floor = min(keep_min, len(msgs))
    dropped = 0
    while dropped < len(msgs) - floor:
        rest = msgs[dropped:]
        if prompt_tokens(
            framework=framework,
            context=context,
            summary=summary,
            messages=rest,
            user_text=user_text,
        ) <= limit:
            return dropped
        dropped += 1
    while dropped < len(msgs) - 1:
        rest = msgs[dropped:]
        if prompt_tokens(
            framework=framework,
            context=context,
            summary=summary,
            messages=rest,
            user_text=user_text,
        ) <= limit:
            return dropped
        dropped += 1
    return dropped


def clip_summary(text: str) -> str:
    body = text.strip()
    if "<summary>" in body.lower():
        lower = body.lower()
        start = lower.find("<summary>")
        end = lower.find("</summary>")
        if start >= 0:
            start += len("<summary>")
            chunk = body[start:end] if end > start else body[start:]
            body = chunk.strip()
    return body[:MAX_SUMMARY_CHARS]


def heuristic_summary(previous: str, discarded: list[Message] | tuple[Message, ...]) -> str:
    if previous.strip():
        return previous.strip()[:MAX_SUMMARY_CHARS]
    bits = [item.content[:40] for item in discarded if item.role == "user" and item.content.strip()]
    return "；".join(bits[:6])

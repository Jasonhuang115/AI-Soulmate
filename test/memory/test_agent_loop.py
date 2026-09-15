from pathlib import Path

from memory.types import RecallContext, TurnRecord
from memory.agent import MemoryAgent


async def test_recall_deadline_returns_cached(tmp_path: Path) -> None:
    agent = MemoryAgent(tmp_path)
    (tmp_path / "MEMORY.md").write_text("我们是朋友", encoding="utf-8")
    first = await agent.recall(RecallContext("最近工作还顺利吗", (), ""), 200)
    assert "朋友" in first.index
    assert first.relationship == ""

    async def slow(_ctx):
        import asyncio

        await asyncio.sleep(1)
        raise AssertionError("should not finish")

    agent._recall = slow  # type: ignore[method-assign]
    again = await agent.recall(RecallContext("那他还喝茶吗", (), ""), 10)
    assert again.index == first.index


async def test_observe_writes_transcript_not_log(tmp_path: Path) -> None:
    agent = MemoryAgent(tmp_path)
    await agent.observe(TurnRecord("t", "我喜欢茶", "好", False))
    assert not list((tmp_path / "logs").glob("*.md"))
    logs = list((tmp_path / "transcripts").glob("*.jsonl"))
    assert logs
    assert "茶" in logs[0].read_text(encoding="utf-8")
    await agent.extract_visit()
    assert not list((tmp_path / "logs").glob("*.md"))


def test_heuristic_dream_dedupes_bullets(tmp_path: Path) -> None:
    agent = MemoryAgent(tmp_path)
    (tmp_path / "relationship.md").write_text("## 状态\n- 朋友\n- 朋友\n- 同事\n", encoding="utf-8")
    agent._heuristic_dream()
    text = (tmp_path / "relationship.md").read_text(encoding="utf-8")
    assert text.count("- 朋友") == 1
    assert "- 同事" in text
    assert (tmp_path / ".changelog.jsonl").exists()


class _FakeCompleter:
    async def complete(self, messages):
        del messages
        return "<summary>\n互称：澄澄\n纠偏与边界：无\n</summary>"


async def test_compress_uses_completer_and_writes_rolling(tmp_path: Path) -> None:
    from asm.core.bus import EventBus
    from asm.core.events import CompressionNeeded, SummaryReady
    from asm.core.interfaces import Message

    bus = EventBus()
    seen: list[str] = []

    async def on_summary(event: SummaryReady) -> None:
        seen.append(event.text)

    bus.subscribe(SummaryReady, on_summary)
    agent = MemoryAgent(tmp_path, completer=_FakeCompleter(), bus=bus)
    await bus.publish(
        CompressionNeeded(
            discarded=(Message(role="user", content="叫你澄澄"),),
            previous_summary="",
        )
    )
    assert seen
    assert "澄澄" in seen[0]
    assert "澄澄" in (tmp_path / "rolling.md").read_text(encoding="utf-8")


async def test_extract_on_disconnect_uses_supervisor(tmp_path: Path) -> None:
    import json
    from datetime import date

    from asm.core.bus import EventBus
    from asm.core.events import ClientConnected, ClientDisconnected, TurnClosed
    from memory.supervisor import CompletionMessage, ToolCallDelta

    today = date.today().isoformat()
    bus = EventBus()
    calls = {"n": 0}

    class LLM:
        async def complete_with_tools(self, messages, tools=None, **kwargs):
            del messages, tools, kwargs
            calls["n"] += 1
            if calls["n"] == 1:
                return CompletionMessage(
                    tool_calls=(
                        ToolCallDelta(
                            "1",
                            "append",
                            json.dumps(
                                {
                                    "rel": f"logs/{today}.md",
                                    "text": "- 他每天喝红茶",
                                }
                            ),
                        ),
                    )
                )
            return CompletionMessage(content="done")

    MemoryAgent(tmp_path, client=LLM(), bus=bus)
    await bus.publish(ClientConnected())
    await bus.publish(
        TurnClosed(
            turn_id="t",
            user_text="我喜欢红茶，每天都喝",
            assistant_text="记下了",
            interrupted=False,
        )
    )
    await bus.publish(ClientDisconnected())
    text = (tmp_path / "logs" / f"{today}.md").read_text(encoding="utf-8")
    assert "红茶" in text
    await bus.publish(ClientDisconnected())
    assert calls["n"] == 2


async def test_extract_skips_hello(tmp_path: Path) -> None:
    from asm.core.bus import EventBus
    from asm.core.events import ClientConnected, ClientDisconnected, TurnClosed
    from memory.supervisor import CompletionMessage

    class LLM:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_with_tools(self, messages, tools=None, **kwargs):
            del messages, tools, kwargs
            self.calls += 1
            return CompletionMessage(content="nope")

    bus = EventBus()
    llm = LLM()
    MemoryAgent(tmp_path, client=llm, bus=bus)
    await bus.publish(ClientConnected())
    await bus.publish(
        TurnClosed(turn_id="t", user_text="你好", assistant_text="嗨", interrupted=False)
    )
    await bus.publish(ClientDisconnected())
    assert llm.calls == 0
    assert not list((tmp_path / "logs").glob("*.md"))
    assert list((tmp_path / "transcripts").glob("*.jsonl"))

from pathlib import Path

from memory.types import RecallContext, TurnRecord
from memory.agent import MemoryAgent


async def test_recall_does_not_run_supervisor(tmp_path: Path) -> None:
    from memory.supervisor import CompletionMessage

    (tmp_path / "MEMORY.md").write_text("我们是朋友\n", encoding="utf-8")

    class LLM:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_with_tools(self, messages, tools=None, **kwargs):
            del messages, tools, kwargs
            self.calls += 1
            return CompletionMessage(content="nope")

    llm = LLM()
    agent = MemoryAgent(tmp_path, client=llm)
    bundle = await agent.recall(RecallContext("晚上喝点什么", (), ""), 2000)
    assert llm.calls == 0
    assert "朋友" in bundle.index
    assert bundle.relationship == ""


async def test_observe_writes_sqlite_not_log(tmp_path: Path) -> None:
    agent = MemoryAgent(tmp_path)
    await agent.observe(TurnRecord("t", "我喜欢茶", "好", False))
    assert not list((tmp_path / "logs").glob("*.md"))
    assert not list((tmp_path / "transcripts").glob("*.jsonl"))
    hits = agent.store.search(pattern="茶")["turns"]
    assert hits
    assert "茶" in hits[0]["user"]


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
    assert agent.tools.read("rolling.md") == ""


async def _await_job(agent: MemoryAgent) -> None:
    task = agent._inflight_consolidate
    if task is not None:
        await task


async def test_consolidate_on_disconnect(tmp_path: Path) -> None:
    import json

    from asm.core.bus import EventBus
    from asm.core.events import ClientConnected, ClientDisconnected, TurnClosed
    from memory.supervisor import CompletionMessage, ToolCallDelta

    bus = EventBus()
    calls = {"n": 0}
    seen_tools: list[list[str]] = []
    prompts: list[str] = []

    class LLM:
        async def complete_with_tools(self, messages, tools=None, **kwargs):
            del kwargs
            prompts.append(messages[1]["content"])
            seen_tools.append(
                [item["function"]["name"] for item in (tools or []) if "function" in item]
            )
            calls["n"] += 1
            if calls["n"] == 1:
                return CompletionMessage(
                    tool_calls=(
                        ToolCallDelta(
                            "1",
                            "write",
                            json.dumps({"rel": "relationship.md", "content": "他每天喝红茶\n"}),
                        ),
                    )
                )
            return CompletionMessage(content="done")

    agent = MemoryAgent(tmp_path, client=LLM(), bus=bus)
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
    await _await_job(agent)
    assert "红茶" in (tmp_path / "relationship.md").read_text(encoding="utf-8")
    assert agent.store.count() == 1
    assert "search_turns" in seen_tools[0]
    assert "append" not in seen_tools[0]
    assert "新增轮次：1" in prompts[0]
    assert agent.dream.last_run() is not None
    await bus.publish(ClientDisconnected())
    await _await_job(agent)
    assert calls["n"] == 2


async def test_zero_new_turns_does_not_start_llm(tmp_path: Path) -> None:
    from asm.core.bus import EventBus
    from asm.core.events import ClientDisconnected
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
    agent = MemoryAgent(tmp_path, client=llm, bus=bus)
    await bus.publish(ClientDisconnected())
    await _await_job(agent)
    assert llm.calls == 0
    assert agent.dream.last_run() is None


async def test_empty_op_advances_last_run(tmp_path: Path) -> None:
    from asm.core.bus import EventBus
    from asm.core.events import ClientDisconnected, TurnClosed
    from memory.supervisor import CompletionMessage

    class LLM:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_with_tools(self, messages, tools=None, **kwargs):
            del messages, tools, kwargs
            self.calls += 1
            return CompletionMessage(content="没什么可写")

    bus = EventBus()
    llm = LLM()
    agent = MemoryAgent(tmp_path, client=llm, bus=bus)
    await bus.publish(
        TurnClosed(turn_id="t", user_text="你好", assistant_text="嗨", interrupted=False)
    )
    await bus.publish(ClientDisconnected())
    await _await_job(agent)
    assert llm.calls == 1
    first = agent.dream.last_run()
    assert first
    await bus.publish(ClientDisconnected())
    await _await_job(agent)
    assert llm.calls == 1
    assert agent.dream.last_run() == first


async def test_exception_does_not_advance_last_run(tmp_path: Path) -> None:
    from asm.core.bus import EventBus
    from asm.core.events import ClientDisconnected, TurnClosed

    class Boom:
        async def complete_with_tools(self, messages, tools=None, **kwargs):
            del messages, tools, kwargs
            raise RuntimeError("llm down")

    bus = EventBus()
    agent = MemoryAgent(tmp_path, client=Boom(), bus=bus)
    await bus.publish(
        TurnClosed(turn_id="t", user_text="我喜欢红茶", assistant_text="好", interrupted=False)
    )
    await bus.publish(ClientDisconnected())
    await _await_job(agent)
    assert agent.dream.last_run() is None


async def test_lock_skips_second_consolidate(tmp_path: Path) -> None:
    from asm.core.bus import EventBus
    from asm.core.events import ClientDisconnected, TurnClosed
    from memory.dream import DreamGate
    from memory.supervisor import CompletionMessage

    class LLM:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_with_tools(self, messages, tools=None, **kwargs):
            del messages, tools, kwargs
            self.calls += 1
            return CompletionMessage(content="ok")

    bus = EventBus()
    llm = LLM()
    gate = DreamGate(tmp_path)
    assert gate.try_acquire()
    agent = MemoryAgent(tmp_path, client=llm, dream=gate, bus=bus)
    await bus.publish(
        TurnClosed(turn_id="t", user_text="我喜欢红茶", assistant_text="好", interrupted=False)
    )
    await bus.publish(ClientDisconnected())
    await _await_job(agent)
    assert llm.calls == 0
    assert agent.dream.last_run() is None
    gate.release()


async def test_recall_requested_does_not_run_supervisor(tmp_path: Path) -> None:
    from asm.core.bus import EventBus
    from asm.core.events import ContextReady, RecallRequested
    from asm.core.interfaces import Message
    from memory.supervisor import CompletionMessage

    class LLM:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_with_tools(self, messages, tools=None, **kwargs):
            del messages, tools, kwargs
            self.calls += 1
            return CompletionMessage(content="nope")

    (tmp_path / "MEMORY.md").write_text("旧小抄\n", encoding="utf-8")
    bus = EventBus()
    seen: list[str] = []

    async def on_ctx(event: ContextReady) -> None:
        seen.append(event.context.index)

    bus.subscribe(ContextReady, on_ctx)
    llm = LLM()
    MemoryAgent(tmp_path, client=llm, bus=bus)
    await bus.publish(
        RecallRequested(text="晚上喝点什么", recent=(Message(role="user", content="hi"),), deadline_ms=2000)
    )
    assert llm.calls == 0
    assert seen
    assert "旧小抄" in seen[0]


async def test_connect_does_not_load_turns_into_session(tmp_path: Path) -> None:
    from asm.core.bus import EventBus
    from asm.core.clock import FakeClock
    from asm.core.events import ClientConnected
    from asm.core.orchestrator import Orchestrator
    from asm.core.session import Session
    from asm.core.interfaces import TurnRequest

    class RecordingBrain:
        async def start_turn(self, req: TurnRequest) -> None:
            del req

        async def cancel(self, turn_id: str) -> None:
            del turn_id

    bus = EventBus()
    session = Session()
    Orchestrator(bus, session, FakeClock(), RecordingBrain())
    agent = MemoryAgent(tmp_path, bus=bus)
    agent.store.append("t", "我喜欢红茶，每天都喝", "好")
    await bus.publish(ClientConnected())
    assert session.messages == []


async def test_connect_loads_rolling_for_acheng_not_tools(tmp_path: Path) -> None:
    from asm.core.bus import EventBus
    from asm.core.events import ClientConnected, SummaryReady

    (tmp_path / "rolling.md").write_text("互称：澄澄\n", encoding="utf-8")
    bus = EventBus()
    seen: list[str] = []

    async def on_summary(event: SummaryReady) -> None:
        seen.append(event.text)

    bus.subscribe(SummaryReady, on_summary)
    agent = MemoryAgent(tmp_path, bus=bus)
    await bus.publish(ClientConnected())
    assert seen
    assert "澄澄" in seen[0]
    assert agent.tools.read("rolling.md") == ""


async def test_no_api_key_does_not_advance_last_run(tmp_path: Path) -> None:
    from asm.core.bus import EventBus
    from asm.core.events import ClientDisconnected, TurnClosed

    bus = EventBus()
    agent = MemoryAgent(tmp_path, client=None, bus=bus)
    await bus.publish(
        TurnClosed(turn_id="t", user_text="我喜欢红茶", assistant_text="好", interrupted=False)
    )
    await bus.publish(ClientDisconnected())
    await _await_job(agent)
    assert agent.dream.last_run() is None

from pathlib import Path

from memory.agent import MemoryAgent
from memory.supervisor import CompletionMessage, MemorySupervisor, ToolCallDelta
from memory.tools import MemoryTools
from memory.types import RecallContext


class ScriptedLLM:
    def __init__(self, turns: list[CompletionMessage]) -> None:
        self.turns = list(turns)
        self.calls = 0
        self.thinking: list[bool] = []

    async def complete_with_tools(self, messages, tools=None, *, thinking=False, temperature=0.3):
        del messages, tools, temperature
        self.calls += 1
        self.thinking.append(thinking)
        if not self.turns:
            return CompletionMessage()
        return self.turns.pop(0)


def _write_call(rel: str, content: str) -> CompletionMessage:
    import json

    return CompletionMessage(
        tool_calls=(
            ToolCallDelta(
                id="1",
                name="write",
                arguments=json.dumps({"rel": rel, "content": content}),
            ),
        )
    )


def _append_call(rel: str, text: str) -> CompletionMessage:
    import json

    return CompletionMessage(
        tool_calls=(
            ToolCallDelta(
                id="1",
                name="append",
                arguments=json.dumps({"rel": rel, "text": text}),
            ),
        )
    )


async def test_supervisor_extract_appends_log(tmp_path: Path) -> None:
    tools = MemoryTools(tmp_path)
    llm = ScriptedLLM(
        [
            _append_call("logs/2026-09-15.md", "- 他喜欢红茶"),
            CompletionMessage(content="done"),
        ]
    )
    supervisor = MemorySupervisor(tools, llm)
    await supervisor.run("extract", "记下来")
    assert "红茶" in (tmp_path / "logs" / "2026-09-15.md").read_text(encoding="utf-8")
    assert llm.thinking == [False, False]


async def test_supervisor_recall_cannot_write_relationship(tmp_path: Path) -> None:
    (tmp_path / "relationship.md").write_text("旧\n", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("工作集\n", encoding="utf-8")
    tools = MemoryTools(tmp_path)
    llm = ScriptedLLM(
        [
            _write_call("relationship.md", "被篡改"),
            CompletionMessage(content="done"),
        ]
    )
    await MemorySupervisor(tools, llm).run("recall", "晋升")
    assert (tmp_path / "relationship.md").read_text(encoding="utf-8") == "旧\n"
    assert (tmp_path / "MEMORY.md").read_text(encoding="utf-8") == "工作集\n"


async def test_supervisor_dream_enables_thinking(tmp_path: Path) -> None:
    llm = ScriptedLLM([CompletionMessage(content="ok")])
    await MemorySupervisor(MemoryTools(tmp_path), llm).run("dream", "巩固")
    assert llm.thinking == [True]


async def test_recall_promotes_memory_md_only(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("刚认识\n", encoding="utf-8")
    (tmp_path / "relationship.md").write_text("档案里有互称澄澄\n", encoding="utf-8")
    llm = ScriptedLLM(
        [
            _write_call("MEMORY.md", "他叫我澄澄\n"),
            CompletionMessage(content="ok"),
        ]
    )
    agent = MemoryAgent(tmp_path, client=llm)
    bundle = await agent.recall(RecallContext("澄澄在吗今晚喝茶", (), ""), 2000)
    assert bundle.index.strip() == "他叫我澄澄"
    assert bundle.relationship == ""
    assert bundle.snippets == ()


async def test_recall_skips_greeting(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("旧工作集\n", encoding="utf-8")
    llm = ScriptedLLM([CompletionMessage(content="nope")])
    agent = MemoryAgent(tmp_path, client=llm)
    bundle = await agent.recall(RecallContext("你好", (), ""), 2000)
    assert llm.calls == 0
    assert "旧工作集" in bundle.index

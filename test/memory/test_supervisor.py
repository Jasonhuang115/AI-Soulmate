from pathlib import Path

from memory.supervisor import CONSOLIDATE, CompletionMessage, KIND_TOOLS, MemorySupervisor, ToolCallDelta
from memory.tools import MemoryTools


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


async def test_supervisor_consolidate_enables_thinking(tmp_path: Path) -> None:
    llm = ScriptedLLM([CompletionMessage(content="ok")])
    await MemorySupervisor(MemoryTools(tmp_path), llm).run(CONSOLIDATE, "巩固")
    assert llm.thinking == [True]


async def test_cannot_write_memory_md_before_type_file(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("旧\n", encoding="utf-8")
    llm = ScriptedLLM(
        [
            _write_call("MEMORY.md", "他叫我澄澄\n"),
            CompletionMessage(content="done"),
        ]
    )
    await MemorySupervisor(MemoryTools(tmp_path), llm).run(CONSOLIDATE, "巩固")
    assert (tmp_path / "MEMORY.md").read_text(encoding="utf-8") == "旧\n"


async def test_memory_md_allowed_after_type_file(tmp_path: Path) -> None:
    llm = ScriptedLLM(
        [
            _write_call("relationship.md", "他叫我澄澄\n"),
            _write_call("MEMORY.md", "他叫我澄澄\n"),
            CompletionMessage(content="done"),
        ]
    )
    await MemorySupervisor(MemoryTools(tmp_path), llm).run(CONSOLIDATE, "巩固")
    assert "澄澄" in (tmp_path / "relationship.md").read_text(encoding="utf-8")
    assert "澄澄" in (tmp_path / "MEMORY.md").read_text(encoding="utf-8")


async def test_search_turns_tool_reads_store(tmp_path: Path) -> None:
    import json

    from memory.turns import TurnStore

    store = TurnStore(tmp_path / "turns.sqlite", jsonl_dir=tmp_path / "none")
    store.append("t", "我每天喝红茶", "记下了", ts="2026-09-15T12:00:00")
    seen: list[list] = []
    script = [
        CompletionMessage(
            tool_calls=(
                ToolCallDelta(
                    "1",
                    "search_turns",
                    json.dumps({"pattern": "红茶", "field": "user"}),
                ),
            )
        ),
        CompletionMessage(content="done"),
    ]

    class LLM:
        calls = 0

        async def complete_with_tools(self, messages, tools=None, **kwargs):
            del tools, kwargs
            self.calls += 1
            seen.append(list(messages))
            return script.pop(0)

    supervisor = MemorySupervisor(MemoryTools(tmp_path), LLM(), turns=store)
    await supervisor.run(CONSOLIDATE, "查")
    tool_msgs = [item for item in seen[1] if item.get("role") == "tool"]
    assert tool_msgs
    assert "红茶" in tool_msgs[0]["content"]
    assert '"truncated": false' in tool_msgs[0]["content"] or '"truncated":false' in tool_msgs[0]["content"]


def test_load_prompt_includes_readonly_soul() -> None:
    from asm.brain.prompt import default_prompts_dir
    from memory.supervisor import load_prompt

    soul = (default_prompts_dir() / "01-soul.md").read_text(encoding="utf-8").strip()
    text = load_prompt(CONSOLIDATE)
    assert soul in text
    assert "只读人设" in text
    assert "persona.md" not in text
    assert "user.md" in text


def test_search_turns_is_on_consolidate() -> None:
    assert set(KIND_TOOLS) == {CONSOLIDATE}
    assert "search_turns" in KIND_TOOLS[CONSOLIDATE]
    assert "append" not in KIND_TOOLS[CONSOLIDATE]


async def test_brain_runtime_does_not_get_search_turns() -> None:
    from asm.brain.runtime import BrainRuntime
    from asm.core.bus import EventBus
    from asm.core.clock import FakeClock

    class Dummy:
        async def stream_chat(self, messages, tools, cancel_event):
            del messages, tools, cancel_event
            if False:
                yield None

    brain = BrainRuntime(EventBus(), FakeClock(), Dummy())  # type: ignore[arg-type]
    assert brain._tools == []
    assert all(getattr(item, "name", None) != "search_turns" for item in brain._tools)


async def test_append_is_not_a_tool(tmp_path: Path) -> None:
    import json

    llm = ScriptedLLM(
        [
            CompletionMessage(
                tool_calls=(
                    ToolCallDelta(
                        "1",
                        "append",
                        json.dumps({"rel": "logs/x.md", "text": "- 不该写"}),
                    ),
                )
            ),
            CompletionMessage(content="done"),
        ]
    )
    await MemorySupervisor(MemoryTools(tmp_path), llm).run(CONSOLIDATE, "巩固")
    assert not (tmp_path / "logs").exists()

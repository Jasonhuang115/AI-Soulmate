from pathlib import Path

from memory.types import RecallContext, TurnRecord
from memory.agent import MemoryAgent


async def test_recall_deadline_returns_cached(tmp_path: Path) -> None:
    agent = MemoryAgent(tmp_path)
    (tmp_path / "relationship.md").write_text("我们是朋友", encoding="utf-8")
    first = await agent.recall(RecallContext("朋友", (), ""), 200)
    assert "朋友" in first.relationship

    async def slow(_ctx):
        import asyncio

        await asyncio.sleep(1)
        raise AssertionError("should not finish")

    agent._recall = slow  # type: ignore[method-assign]
    again = await agent.recall(RecallContext("x", (), ""), 10)
    assert again.relationship == first.relationship


async def test_observe_appends_log(tmp_path: Path) -> None:
    agent = MemoryAgent(tmp_path)
    await agent.observe(TurnRecord("t", "我喜欢茶", "好", False))
    logs = list((tmp_path / "logs").glob("*.md"))
    assert logs
    assert "茶" in logs[0].read_text(encoding="utf-8")


def test_heuristic_dream_dedupes_bullets(tmp_path: Path) -> None:
    agent = MemoryAgent(tmp_path)
    (tmp_path / "relationship.md").write_text("## 状态\n- 朋友\n- 朋友\n- 同事\n", encoding="utf-8")
    agent._heuristic_dream()
    text = (tmp_path / "relationship.md").read_text(encoding="utf-8")
    assert text.count("- 朋友") == 1
    assert "- 同事" in text
    assert (tmp_path / ".changelog.jsonl").exists()

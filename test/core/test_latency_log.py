from pathlib import Path

from asm.core.bus import EventBus
from asm.core.events import LatencyMark
from asm.core.latency_log import LatencyLogger


async def test_latency_logger_appends(tmp_path: Path) -> None:
    bus = EventBus()
    path = tmp_path / "latency.jsonl"
    LatencyLogger(bus, path)
    await bus.publish(LatencyMark("t1", {"t_submit": 1.0, "t_first_audio": 1.4}))
    text = path.read_text(encoding="utf-8")
    assert "t1" in text
    assert "t_first_audio" in text

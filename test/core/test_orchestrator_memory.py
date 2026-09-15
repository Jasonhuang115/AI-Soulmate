from asm.core.bus import EventBus
from asm.core.clock import FakeClock
from asm.core.events import CompressionNeeded
from asm.core.interfaces import Message
from asm.core.orchestrator import Orchestrator
from asm.core.session import Session
from memory.stub import StubMemory


class RecordingBrain:
    async def start_turn(self, req) -> None:
        del req

    async def cancel(self, turn_id: str) -> None:
        del turn_id


class CompressingMemory(StubMemory):
    async def compress(self, messages: list[Message]) -> str:
        del messages
        return "早些时候聊过天气"


async def test_compression_updates_summary() -> None:
    bus = EventBus()
    session = Session()
    Orchestrator(bus, session, FakeClock(), RecordingBrain())
    CompressingMemory(bus)
    await bus.publish(CompressionNeeded(messages=(Message(role="user", content="hi"),)))
    assert session.session_summary == "早些时候聊过天气"

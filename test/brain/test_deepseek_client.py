import asyncio
from types import SimpleNamespace

from asm.brain.deepseek_client import DeepSeekClient, TokenEvent
from asm.core.config import Settings
from asm.core.interfaces import Message


class FakeStream:
    def __init__(self, chunks: list[object]) -> None:
        self._chunks = list(chunks)
        self.closed = False

    def __aiter__(self) -> FakeStream:
        return self

    async def __anext__(self) -> object:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)

    async def close(self) -> None:
        self.closed = True


class FakeCompletions:
    def __init__(self, stream: FakeStream) -> None:
        self.stream = stream
        self.kwargs: dict | None = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.stream


def _chunk(content: str | None = None) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


async def test_stream_chat_disables_thinking_and_yields_text() -> None:
    stream = FakeStream([_chunk("你"), _chunk("好")])
    completions = FakeCompletions(stream)
    client = DeepSeekClient(Settings(deepseek_api_key="x"), client=SimpleNamespace(  # type: ignore[arg-type]
        chat=SimpleNamespace(completions=completions)
    ))
    cancel = asyncio.Event()
    events = [
        event
        async for event in client.stream_chat([Message(role="user", content="hi")], [], cancel)
    ]
    assert events == [TokenEvent(kind="text", text="你"), TokenEvent(kind="text", text="好")]
    assert completions.kwargs is not None
    assert completions.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert completions.kwargs["stream"] is True
    assert completions.kwargs["model"] == "deepseek-flash"
    assert stream.closed is True


async def test_stream_chat_stops_on_cancel() -> None:
    stream = FakeStream([_chunk("你"), _chunk("好")])
    completions = FakeCompletions(stream)
    client = DeepSeekClient(Settings(deepseek_api_key="x"), client=SimpleNamespace(  # type: ignore[arg-type]
        chat=SimpleNamespace(completions=completions)
    ))
    cancel = asyncio.Event()
    agen = client.stream_chat([Message(role="user", content="hi")], [], cancel)
    first = await agen.__anext__()
    assert first.text == "你"
    cancel.set()
    rest = [event async for event in agen]
    assert rest == []

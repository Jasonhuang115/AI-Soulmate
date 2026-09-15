import os
from types import SimpleNamespace

import pytest

from asm.core.config import Settings
from asm.voice.volcengine_tts import VolcengineTTS


def test_closed_socket_is_not_reused() -> None:
    engine = VolcengineTTS(Settings())
    engine._ws = SimpleNamespace(state=SimpleNamespace(name="CLOSED"))
    assert engine._is_open() is False
    engine._ws = SimpleNamespace(state=SimpleNamespace(name="OPEN"))
    assert engine._is_open() is True


@pytest.mark.integration
async def test_volcengine_hello() -> None:
    if not os.getenv("VOLC_TTS_ACCESS_KEY"):
        pytest.skip("no volc key")
    engine = VolcengineTTS(Settings())
    chunks = [chunk async for chunk in engine.synthesize("t", 0, "你好")]
    assert chunks
    assert any(chunk.pcm16 for chunk in chunks)

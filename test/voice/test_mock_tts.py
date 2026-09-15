from asm.voice.mock import MockTTS


async def test_mock_tts_yields_pcm() -> None:
    engine = MockTTS()
    chunks = [chunk async for chunk in engine.synthesize("t", 0, "你好")]
    assert len(chunks) == 1
    assert chunks[0].pcm16
    assert chunks[0].sample_rate == 24000
    assert chunks[0].mouth_energy


async def test_mock_tts_cancel() -> None:
    engine = MockTTS()
    await engine.cancel("t")
    chunks = [chunk async for chunk in engine.synthesize("t", 0, "你好")]
    assert chunks == []

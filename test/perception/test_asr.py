import pytest

from asm.perception.paths import asr_dir


@pytest.mark.integration
def test_asr_model_loads_when_present() -> None:
    folder = asr_dir()
    if not (folder / "tokens.txt").exists():
        pytest.skip("zipformer not downloaded")
    from asm.perception.asr_sherpa import load_asr
    from asm.perception.vad_silero import load_vad

    assert load_vad() is not None
    assert load_asr() is not None

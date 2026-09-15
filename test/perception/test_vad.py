from pathlib import Path

import pytest

from asm.perception.paths import vad_path


@pytest.mark.integration
def test_vad_model_present_or_skip() -> None:
    if not vad_path().exists():
        pytest.skip("silero vad not downloaded")
    assert Path(vad_path()).stat().st_size > 0

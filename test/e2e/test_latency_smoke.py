import pytest


@pytest.mark.integration
def test_latency_smoke_placeholder() -> None:
    pytest.skip("needs local ASR models and a recorded wav")

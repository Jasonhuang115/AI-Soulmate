from fastapi.testclient import TestClient

from asm.app import create_app
from asm.core.config import Settings


def _app():
    return create_app(
        Settings(
            impulse_enabled=False,
            deepseek_api_key="",
            volc_tts_api_key="",
            volc_tts_access_key="",
            volc_tts_app_key="",
        )
    )


def test_health() -> None:
    client = TestClient(_app())
    body = client.get("/health").json()
    assert body["ok"] == "1"
    assert body["brain"] == "mock"
    assert body["speak"] == "mock"
    assert body["listen"] in {"off", "sherpa"}


def test_ws_text_roundtrip() -> None:
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "text_input", "text": "你好"})
        texts: list[str] = []
        saw_thinking = False
        for _ in range(80):
            msg = ws.receive_json()
            if msg.get("type") == "state" and msg.get("state") == "thinking":
                saw_thinking = True
            if msg.get("type") == "text_delta":
                texts.append(msg["text"])
            if msg.get("type") == "state" and msg.get("state") == "idle" and texts:
                break
        assert saw_thinking
        assert "".join(texts) == "你刚才说：你好。"

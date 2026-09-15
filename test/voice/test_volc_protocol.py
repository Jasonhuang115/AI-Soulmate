from asm.voice.volc_protocol import (
    EVENT_FINISH_SESSION,
    EVENT_START_CONNECTION,
    EVENT_START_SESSION,
    EVENT_TASK_REQUEST,
    encode_event,
    parse_frame,
    session_payload,
)


def test_encode_parse_start_connection() -> None:
    frame = encode_event(EVENT_START_CONNECTION, payload={})
    parsed = parse_frame(frame)
    assert parsed.event == EVENT_START_CONNECTION


def test_session_payload_is_pcm() -> None:
    payload = session_payload("你好", "speaker-a", EVENT_TASK_REQUEST)
    assert payload["req_params"]["audio_params"]["format"] == "pcm"
    frame = encode_event(EVENT_START_SESSION, "abc", payload)
    parsed = parse_frame(frame)
    assert parsed.event == EVENT_START_SESSION
    assert parsed.session_id == "abc"


def test_finish_session_includes_payload_size() -> None:
    frame = encode_event(EVENT_FINISH_SESSION, "abc")
    parsed = parse_frame(frame)
    assert parsed.event == EVENT_FINISH_SESSION
    assert parsed.session_id == "abc"
    # header(4) + event(4) + sid_len(4) + "abc"(3) + payload_len(4)
    assert len(frame) == 19

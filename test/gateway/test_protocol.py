from asm.core.events import (
    Cancel,
    DialogState,
    PartialTranscript,
    PlaybackDone,
    SpokenProgress,
    StateChanged,
    TextDelta,
    TextInput,
)
from asm.gateway.protocol import encode_outbound, parse_inbound


def test_parse_text_input() -> None:
    event = parse_inbound('{"type":"text_input","text":"你好"}')
    assert isinstance(event, TextInput)
    assert event.text == "你好"


def test_parse_invalid_json() -> None:
    assert parse_inbound("{") is None
    assert parse_inbound('{"type":"unknown"}') is None
    assert parse_inbound("[]") is None


def test_parse_playback_done() -> None:
    event = parse_inbound('{"type":"playback_done","turn_id":"t1"}')
    assert isinstance(event, PlaybackDone)
    assert event.turn_id == "t1"
    assert parse_inbound('{"type":"playback_done"}') is None


def test_parse_spoken_progress() -> None:
    event = parse_inbound('{"type":"spoken_progress","turn_id":"t1","sentence_idx":2}')
    assert isinstance(event, SpokenProgress)
    assert event.sentence_idx == 2


def test_encode_text_delta() -> None:
    raw = encode_outbound(TextDelta(turn_id="abc", text="你"))
    assert raw is not None
    assert '"text_delta"' in raw
    assert "abc" in raw


def test_encode_state_and_cancel() -> None:
    assert encode_outbound(StateChanged(DialogState.THINKING)) == '{"type": "state", "state": "thinking"}'
    assert encode_outbound(Cancel("t1")) == '{"type": "cancel", "turn_id": "t1"}'


def test_encode_partial_transcript() -> None:
    raw = encode_outbound(PartialTranscript("你好"))
    assert raw is not None
    assert "partial_transcript" in raw
    assert "你好" in raw


def test_encode_avatar_command_motions() -> None:
    from asm.core.events import AvatarCommand

    raw = encode_outbound(
        AvatarCommand("t1", 0, "happy", ("wave", "bow"), None, None, True)
    )
    assert raw is not None
    assert '"motions": ["wave", "bow"]' in raw
    assert '"motion": "wave"' in raw
    assert '"immediate": true' in raw

from asm.brain.tool_parser import (
    EmotionStripper,
    Marker,
    group_markers,
    strip_emotion_markers,
)


def test_strip_canonical_markers() -> None:
    text, markers = strip_emotion_markers("你好⟦happy⟧世界[playful]。")
    assert "⟦" not in text
    assert "[" not in text
    assert markers == [Marker("emotion", "happy"), Marker("emotion", "playful")]
    assert "你好" in text and "世界" in text


def test_strip_motion_markers() -> None:
    text, markers = strip_emotion_markers("嗨⟦happy⟧⟦wave⟧。")
    assert text == "嗨。"
    assert markers == [Marker("emotion", "happy"), Marker("motion", "wave")]
    only_motion, tagged = strip_emotion_markers("点头⟦nod⟧")
    assert only_motion == "点头"
    assert tagged == [Marker("motion", "nod")]
    look, look_m = strip_emotion_markers("躲开⟦look_away⟧")
    assert look == "躲开"
    assert look_m == [Marker("motion", "look_away")]


def test_strip_legacy_keyed_tags_without_teaching_them() -> None:
    text, markers = strip_emotion_markers("你又来了[emo=playful][demo=happy]。")
    assert "[" not in text
    assert markers == [Marker("emotion", "playful"), Marker("emotion", "happy")]
    assert "你又来了" in text
    junk, empty = strip_emotion_markers("旁白[foo=bar]完")
    assert junk == "旁白完"
    assert empty == []
    kept, none = strip_emotion_markers("见[ok]面")
    assert kept == "见[ok]面"
    assert none == []


def test_stripper_holds_incomplete_marker() -> None:
    stripper = EmotionStripper()
    cleaned, markers = stripper.feed("你好。⟦")
    assert "⟦" not in cleaned
    assert markers == []
    assert "你好。" in cleaned
    cleaned, markers = stripper.feed("happy⟧")
    assert cleaned == ""
    assert markers == [Marker("emotion", "happy")]


def test_stripper_holds_underscored_motion() -> None:
    stripper = EmotionStripper()
    cleaned, markers = stripper.feed("嗯。⟦look_")
    assert cleaned == "嗯。"
    assert markers == []
    cleaned, markers = stripper.feed("away⟧")
    assert cleaned == ""
    assert markers == [Marker("motion", "look_away")]


def test_stripper_flush() -> None:
    stripper = EmotionStripper()
    cleaned, markers = stripper.feed("尾句⟦sad⟧")
    assert cleaned == "尾句"
    assert markers == [Marker("emotion", "sad")]
    leftover, extra = stripper.flush()
    assert leftover == ""
    assert extra == []


def test_group_markers_pairs_motion_with_emotion() -> None:
    assert group_markers(
        [Marker("emotion", "happy"), Marker("motion", "wave")]
    ) == [("happy", "wave")]
    assert group_markers([Marker("motion", "nod")]) == [(None, "nod")]
    assert group_markers(
        [Marker("emotion", "happy"), Marker("motion", "wave"), Marker("emotion", "sad")]
    ) == [("happy", "wave"), ("sad", None)]

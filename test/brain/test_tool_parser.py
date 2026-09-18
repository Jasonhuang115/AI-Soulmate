from asm.brain.tool_parser import (
    EmotionStripper,
    Marker,
    collect_tags,
    last_now_body,
    parse_parts,
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


def test_strip_stop() -> None:
    text, markers = strip_emotion_markers("够了⟦stop⟧")
    assert text == "够了"
    assert markers == [Marker("control", "stop")]


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


def test_collect_tags_keeps_three_motions() -> None:
    tags = collect_tags(
        [
            Marker("emotion", "happy"),
            Marker("motion", "bow"),
            Marker("motion", "wave"),
            Marker("motion", "nod"),
            Marker("motion", "clap"),
        ]
    )
    assert tags.emotion == "happy"
    assert tags.motions == ("bow", "wave", "nod")


def test_parse_parts_keeps_order() -> None:
    parts = parse_parts("⟦wave⟧好。⟦happy⟧")
    assert parts[0] == Marker("motion", "wave")
    assert parts[1] == "好。"
    assert parts[2] == Marker("emotion", "happy")


def test_strip_now_marker_and_keep_last() -> None:
    text, markers = strip_emotion_markers(
        "嗯。⟦happy⟧⟦此刻 有点委屈，他刚才那句话⟧⟦wave⟧"
    )
    assert text == "嗯。"
    assert "⟦" not in text
    assert Marker("now", "有点委屈，他刚才那句话") in markers
    assert Marker("emotion", "happy") in markers
    assert Marker("motion", "wave") in markers
    assert last_now_body("先⟦此刻 有点闷⟧再⟦此刻 被那句话刺到⟧") == "被那句话刺到"


def test_now_empty_or_scale_is_dropped() -> None:
    empty, markers = strip_emotion_markers("嗯⟦此刻 ⟧。")
    assert empty == "嗯。"
    assert markers == []
    scaled, scaled_m = strip_emotion_markers("嗯⟦此刻 valence 0.6⟧")
    assert scaled == "嗯"
    assert scaled_m == []
    score, score_m = strip_emotion_markers("嗯⟦此刻 心情值4分⟧")
    assert score == "嗯"
    assert score_m == []
    ok, ok_m = strip_emotion_markers("嗯⟦此刻 有点过分，他刚才那句⟧")
    assert ok == "嗯"
    assert ok_m == [Marker("now", "有点过分，他刚才那句")]


def test_now_truncates_sentence_and_length() -> None:
    _, markers = strip_emotion_markers("⟦此刻 先委屈。然后又开心⟧")
    assert markers == [Marker("now", "先委屈。")]
    long_body = "他" * 50
    _, long_m = strip_emotion_markers(f"⟦此刻 {long_body}⟧")
    assert long_m[0].kind == "now"
    assert len(long_m[0].name) == 40


def test_stripper_holds_now_and_drops_unclosed_on_flush() -> None:
    stripper = EmotionStripper()
    cleaned, markers = stripper.feed("嗯。⟦此刻 ")
    assert cleaned == "嗯。"
    assert markers == []
    cleaned, markers = stripper.feed("有点委屈⟧")
    assert cleaned == ""
    assert markers == [Marker("now", "有点委屈")]
    dangling = EmotionStripper()
    cleaned, markers = dangling.feed("尾句⟦此刻 有")
    assert cleaned == "尾句"
    leftover, extra = dangling.flush()
    assert leftover == ""
    assert extra == []
    assert "⟦" not in leftover


def test_collect_tags_ignores_now() -> None:
    tags = collect_tags([Marker("now", "有点委屈"), Marker("emotion", "sad")])
    assert tags.emotion == "sad"
    assert tags.motions == ()
    only_now = collect_tags([Marker("now", "有点委屈")])
    assert only_now.empty

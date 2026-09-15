from embodiment.mapper import translate


def test_translate_and_fallback() -> None:
    mapping = {
        "expressions": {"happy": "F03", "neutral": "F01"},
        "motions": {"nod": {"group": "Tap", "index": 1}},
        "fallback_expression": "neutral",
    }
    hit = translate("happy", "nod", mapping)
    assert hit["expression_id"] == "F03"
    assert hit["group"] == "Tap"
    miss = translate("sad", "wave", mapping)
    assert miss["expression_id"] == "F01"
    assert miss["group"] is None

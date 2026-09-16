from random import Random

from embodiment.rules import apply_rule
from embodiment.vocab import EMOTIONS, MOTIONS


def test_emotion_and_motion_vocab_are_disjoint() -> None:
    assert not set(EMOTIONS) & set(MOTIONS)


def test_unknown_falls_back_to_neutral() -> None:
    applied = apply_rule("ragequit")
    assert applied.expression == "neutral"


def test_agree_is_nod() -> None:
    applied = apply_rule("agree")
    assert applied.expression is None
    assert applied.motion == "nod"


def test_happy_motion_in_set() -> None:
    applied = apply_rule("happy", rng=Random(0))
    assert applied.expression == "happy"
    assert applied.motion in {"wave", "clap", "jump"}


def test_explicit_motion_overrides_rule() -> None:
    applied = apply_rule("happy", rng=Random(0), motion="wave")
    assert applied.expression == "happy"
    assert applied.motion == "wave"


def test_motion_only_keeps_expression_empty() -> None:
    applied = apply_rule(motion="nod")
    assert applied.expression is None
    assert applied.motion == "nod"

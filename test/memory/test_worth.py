from pathlib import Path

from memory.worth import is_phatic, skip_extract, skip_recall


def test_phatic_greetings() -> None:
    assert is_phatic("你好")
    assert is_phatic("在吗")
    assert is_phatic("嗯嗯")
    assert is_phatic("[系统：你想主动说点什么，原因：idle]")
    assert not is_phatic("我喜欢红茶")
    assert not is_phatic("其实最近睡得不好")


def test_skip_recall_same_sentence() -> None:
    assert skip_recall("今晚还喝茶吗", "今晚还喝茶吗")
    assert not skip_recall("今晚还喝茶吗", "今晚喝什么")


def test_skip_extract_when_only_hello() -> None:
    assert skip_extract([])
    assert skip_extract([{"user": "你好"}, {"user": "在吗"}])
    assert not skip_extract([{"user": "我喜欢红茶，每天都喝"}])

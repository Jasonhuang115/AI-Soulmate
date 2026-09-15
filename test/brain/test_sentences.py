from asm.brain.sentences import SentenceSplitter


def test_two_sentences_in_one_chunk() -> None:
    splitter = SentenceSplitter()
    assert splitter.feed("你好。我在。") == ["你好。", "我在。"]


def test_short_flush() -> None:
    splitter = SentenceSplitter()
    assert splitter.feed("嗯") == []
    assert splitter.flush() == "嗯"


def test_short_first_sentence_waits() -> None:
    splitter = SentenceSplitter(first_min_chars=4)
    assert splitter.feed("啊。") == []
    assert splitter.flush() == "啊。"


def test_first_sentence_cuts_at_four_chars() -> None:
    splitter = SentenceSplitter(first_min_chars=4)
    assert splitter.feed("今天不错。") == ["今天不错。"]


def test_decimal_not_split() -> None:
    splitter = SentenceSplitter(first_min_chars=4)
    assert splitter.feed("等一下3.14秒。") == ["等一下3.14秒。"]

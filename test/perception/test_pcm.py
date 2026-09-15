from asm.perception.pcm import PcmFramer


def test_framer_splits_and_buffers() -> None:
    framer = PcmFramer(4)
    assert framer.push(b"ab") == []
    assert framer.push(b"cdefgh") == [b"abcd", b"efgh"]

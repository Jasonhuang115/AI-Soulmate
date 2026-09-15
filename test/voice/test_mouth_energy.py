import math
import struct

from asm.voice.mouth_energy import mouth_energy


def test_silence_is_zero() -> None:
    pcm = struct.pack("<" + "h" * 480, *([0] * 480))
    assert mouth_energy(pcm, 24000) == [0.0]


def test_sine_has_energy() -> None:
    samples = [int(20000 * math.sin(2 * math.pi * 220 * i / 24000)) for i in range(480)]
    pcm = struct.pack("<" + "h" * 480, *samples)
    values = mouth_energy(pcm, 24000)
    assert values
    assert max(values) == 1.0
    assert min(values) > 0

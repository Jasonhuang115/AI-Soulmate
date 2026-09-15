from __future__ import annotations

import math
import struct


def mouth_energy(pcm16: bytes, sample_rate: int, hop_ms: int = 20) -> list[float]:
    if not pcm16 or sample_rate <= 0:
        return []
    hop = max(int(sample_rate * hop_ms / 1000), 1)
    samples = struct.unpack("<" + "h" * (len(pcm16) // 2), pcm16[: len(pcm16) // 2 * 2])
    if not samples:
        return []
    energies: list[float] = []
    for start in range(0, len(samples), hop):
        window = samples[start : start + hop]
        mean_sq = sum(s * s for s in window) / len(window)
        energies.append(math.sqrt(mean_sq))
    peak = max(energies) if energies else 0.0
    if peak <= 0:
        return [0.0 for _ in energies]
    return [value / peak for value in energies]

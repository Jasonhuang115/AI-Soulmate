from __future__ import annotations

_SEPS = set("。！？；…\n!?")


class SentenceSplitter:
    def __init__(self, first_min_chars: int = 4, later_min_chars: int = 8) -> None:
        self.first_min_chars = first_min_chars
        self.later_min_chars = later_min_chars
        self._buf = ""
        self._emitted = 0

    def feed(self, delta: str) -> list[str]:
        if not delta:
            return []
        self._buf += delta
        out: list[str] = []
        while True:
            cut = self._find_cut()
            if cut is None:
                break
            sentence = self._buf[:cut].strip()
            self._buf = self._buf[cut:]
            if sentence:
                out.append(sentence)
                self._emitted += 1
        return out

    def flush(self) -> str | None:
        text = self._buf.strip()
        self._buf = ""
        if not text:
            return None
        self._emitted += 1
        return text

    def _min_chars(self) -> int:
        return self.first_min_chars if self._emitted == 0 else self.later_min_chars

    def _char_count(self, text: str) -> int:
        return sum(1 for ch in text if not ch.isspace())

    def _is_decimal_dot(self, index: int) -> bool:
        if self._buf[index] != ".":
            return False
        left = index > 0 and self._buf[index - 1].isdigit()
        right = index + 1 < len(self._buf) and self._buf[index + 1].isdigit()
        return left and right

    def _has_later_separator(self, after: int) -> bool:
        i = after
        while i < len(self._buf):
            if self._buf[i] in _SEPS and not self._is_decimal_dot(i):
                return True
            i += 1
        return False

    def _find_cut(self) -> int | None:
        min_chars = self._min_chars()
        for i, ch in enumerate(self._buf):
            if ch not in _SEPS:
                continue
            if self._is_decimal_dot(i):
                continue
            end = i + 1
            content = self._buf[:end].strip()
            if not content:
                continue
            long_enough = self._char_count(content) >= min_chars
            later = self._has_later_separator(end)
            later_complete = self._emitted > 0
            if long_enough or later or later_complete:
                return end
        return None

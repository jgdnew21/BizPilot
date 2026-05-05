from __future__ import annotations

from app.domain.extraction import NormalizedText


class TextNormalizer:
    _char_map = str.maketrans({
        "，": ",",
        "。": ".",
        "；": ";",
        "：": ":",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
    })

    def normalize(self, text: str) -> NormalizedText:
        raw_text = text
        normalized = text.translate(self._char_map)
        normalized = " ".join(normalized.split())
        return NormalizedText(raw_text=raw_text, normalized_text=normalized)

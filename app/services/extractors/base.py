from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.extraction import ExtractionResult, NormalizedText


class BaseMaterialRequestExtractor(ABC):
    name: str

    @abstractmethod
    def extract(self, normalized_text: NormalizedText) -> ExtractionResult:
        raise NotImplementedError

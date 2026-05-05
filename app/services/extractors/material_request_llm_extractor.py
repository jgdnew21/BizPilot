from __future__ import annotations

from app.domain.extraction import ExtractionResult, NormalizedText
from app.services.extractors.base import BaseMaterialRequestExtractor


class LlmMaterialRequestExtractor(BaseMaterialRequestExtractor):
    """
    Safety constraints for future LLM integration:
    - LLM only generates candidate structured fields.
    - LLM output must pass Pydantic validation.
    - LLM output must pass master-data matching.
    - LLM output must pass BusinessValidator.
    - LLM is not allowed to submit to ERPNext directly.
    - User final confirmation is based on markdown snapshot only.
    """

    name = "llm_placeholder"

    def extract(self, normalized_text: NormalizedText) -> ExtractionResult:
        return ExtractionResult(
            raw_text=normalized_text.raw_text,
            normalized_text=normalized_text.normalized_text,
            extractor_name=self.name,
            warnings=["LLM extractor is not enabled."],
        )

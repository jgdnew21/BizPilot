from __future__ import annotations

from app.config import settings
from app.domain.extraction import ExtractionResult, NormalizedText
from app.services.extractors.base import BaseMaterialRequestExtractor
from app.services.extractors.material_request_llm_extractor import LlmMaterialRequestExtractor
from app.services.extractors.material_request_rule_extractor import RuleBasedMaterialRequestExtractor


class MaterialRequestExtractorOrchestrator:
    def __init__(
        self,
        rule_extractor: BaseMaterialRequestExtractor | None = None,
        llm_extractor: BaseMaterialRequestExtractor | None = None,
    ):
        self.rule_extractor = rule_extractor or RuleBasedMaterialRequestExtractor()
        self.llm_extractor = llm_extractor or LlmMaterialRequestExtractor()

    def extract(self, normalized_text: NormalizedText) -> ExtractionResult:
        if not settings.enable_llm_extractor:
            return self.rule_extractor.extract(normalized_text)

        try:
            llm_result = self.llm_extractor.extract(normalized_text)
            if any(warning.startswith("LLM extraction failed:") for warning in llm_result.warnings):
                raise RuntimeError("; ".join(llm_result.warnings))
            return llm_result
        except Exception as exc:
            rule_result = self.rule_extractor.extract(normalized_text)
            rule_result.warnings.append(f"LLM extraction failed; fallback to rule extractor: {str(exc)}")
            return rule_result

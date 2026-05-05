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

    @staticmethod
    def _is_complete(result: ExtractionResult) -> bool:
        return bool(result.items) and bool(result.supplier_input) and bool(result.schedule_date_input) and bool(result.warehouse_input)

    def extract(self, normalized_text: NormalizedText) -> ExtractionResult:
        rule_result = self.rule_extractor.extract(normalized_text)
        if self._is_complete(rule_result):
            return rule_result

        if settings.enable_llm_extractor:
            llm_result = self.llm_extractor.extract(normalized_text)
            if llm_result.items or llm_result.supplier_input or llm_result.schedule_date_input or llm_result.warehouse_input:
                return llm_result
            rule_result.warnings.extend(llm_result.warnings)

        if "Rule extraction incomplete; LLM fallback is not enabled yet." not in rule_result.warnings and not settings.enable_llm_extractor:
            rule_result.warnings.append("Rule extraction incomplete; LLM fallback is not enabled yet.")
        return rule_result

from app.domain.extraction import ExtractionResult, NormalizedText
from app.domain.purchase.material_request import PurchaseLineInput
from app.services.extractors.material_request_extractor_orchestrator import MaterialRequestExtractorOrchestrator
from app.services.extractors.material_request_llm_extractor import LlmMaterialRequestExtractor
from app.services.extractors.material_request_rule_extractor import RuleBasedMaterialRequestExtractor


def test_rule_extractor_used_by_default(monkeypatch):
    monkeypatch.setattr('app.config.settings.enable_llm_extractor', False)
    orchestrator = MaterialRequestExtractorOrchestrator()
    assert isinstance(orchestrator.rule_extractor, RuleBasedMaterialRequestExtractor)
    assert isinstance(orchestrator.llm_extractor, LlmMaterialRequestExtractor)


def test_orchestrator_uses_rule_when_llm_disabled(monkeypatch):
    monkeypatch.setattr('app.config.settings.enable_llm_extractor', False)
    orchestrator = MaterialRequestExtractorOrchestrator()

    called = {'llm': False}

    def _llm_extract(_):
        called['llm'] = True
        return ExtractionResult(raw_text='x', normalized_text='x', extractor_name='llm_placeholder')

    monkeypatch.setattr(orchestrator.llm_extractor, 'extract', _llm_extract)
    normalized = NormalizedText(raw_text='明天找采无忧采购大米20袋入南宁仓', normalized_text='明天找采无忧采购大米20袋入南宁仓')
    result = orchestrator.extract(normalized)

    assert result.extractor_name == "rule_based"
    assert called['llm'] is False


def test_orchestrator_uses_llm_when_enabled(monkeypatch):
    monkeypatch.setattr('app.config.settings.enable_llm_extractor', True)
    orchestrator = MaterialRequestExtractorOrchestrator()
    normalized = NormalizedText(raw_text='明天采购五常大米80斤，供应商采无忧，入南宁仓', normalized_text='明天采购五常大米80斤，供应商采无忧，入南宁仓')

    monkeypatch.setattr(orchestrator.llm_extractor, "extract", lambda _: ExtractionResult(
        raw_text=normalized.raw_text, normalized_text=normalized.normalized_text, extractor_name="llm",
        supplier_input="采无忧", schedule_date_input="明天", warehouse_input="南宁仓",
        items=[PurchaseLineInput(item_input_name="五常大米", qty=80, uom="斤")]
    ))
    result = orchestrator.extract(normalized)
    assert result.extractor_name == "llm"
    assert result.items[0].item_input_name == "五常大米"


def test_orchestrator_fallbacks_to_rule_when_llm_fails(monkeypatch):
    monkeypatch.setattr('app.config.settings.enable_llm_extractor', True)
    orchestrator = MaterialRequestExtractorOrchestrator()
    normalized = NormalizedText(raw_text='明天采购五常大米80斤，供应商采无忧，入南宁仓', normalized_text='明天采购五常大米80斤，供应商采无忧，入南宁仓')
    monkeypatch.setattr(orchestrator.llm_extractor, "extract", lambda _: (_ for _ in ()).throw(RuntimeError("timeout")))

    result = orchestrator.extract(normalized)
    assert result.extractor_name == "rule_based"
    assert any("fallback to rule extractor" in w for w in result.warnings)

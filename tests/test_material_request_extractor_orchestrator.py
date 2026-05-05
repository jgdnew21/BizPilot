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


def test_orchestrator_returns_rule_result_when_complete(monkeypatch):
    monkeypatch.setattr('app.config.settings.enable_llm_extractor', False)
    orchestrator = MaterialRequestExtractorOrchestrator()

    called = {'llm': False}

    def _llm_extract(_):
        called['llm'] = True
        return ExtractionResult(raw_text='x', normalized_text='x', extractor_name='llm_placeholder')

    monkeypatch.setattr(orchestrator.llm_extractor, 'extract', _llm_extract)
    normalized = NormalizedText(raw_text='明天找采无忧采购大米20袋入南宁仓', normalized_text='明天找采无忧采购大米20袋入南宁仓')
    result = orchestrator.extract(normalized)

    assert result.items
    assert result.supplier_input
    assert result.schedule_date_input
    assert result.warehouse_input
    assert called['llm'] is False


def test_orchestrator_warns_when_rule_incomplete_and_llm_disabled(monkeypatch):
    monkeypatch.setattr('app.config.settings.enable_llm_extractor', False)
    orchestrator = MaterialRequestExtractorOrchestrator()
    normalized = NormalizedText(raw_text='帮我补点货', normalized_text='帮我补点货')

    result = orchestrator.extract(normalized)

    assert 'Rule extraction incomplete; LLM fallback is not enabled yet.' in result.warnings


def test_llm_placeholder_does_not_call_external_service(monkeypatch):
    monkeypatch.setattr('requests.get', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('should not call requests.get')))
    monkeypatch.setattr('requests.post', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('should not call requests.post')))
    extractor = LlmMaterialRequestExtractor()

    normalized = NormalizedText(raw_text='老板说今天先把常用货备一下', normalized_text='老板说今天先把常用货备一下')
    result = extractor.extract(normalized)

    assert result.items == []
    assert result.extractor_name == 'llm_placeholder'
    assert 'LLM extractor is not enabled.' in result.warnings

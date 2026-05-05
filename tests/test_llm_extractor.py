import pytest
import requests

from app.domain.extraction import NormalizedText
from app.services.extractors.material_request_llm_extractor import LlmMaterialRequestExtractor
from app.services.llm_client import LlmClient, LlmRequestError


class DummyClient:
    def __init__(self, payload):
        self.payload = payload

    def chat_json(self, system_prompt: str, user_prompt: str):
        return self.payload


def test_llm_extractor_parses_valid_json():
    extractor = LlmMaterialRequestExtractor(
        llm_client=DummyClient(
            {
                "intent": "create_material_request",
                "confidence": 0.91,
                "schedule_date_input": "明天",
                "supplier_input": "采无忧",
                "warehouse_input": None,
                "items": [{"item_input_name": "五常大米", "qty": 80, "uom": "斤", "evidence": "五常大米 80斤"}],
                "missing_fields": [],
                "warnings": [],
            }
        )
    )
    result = extractor.extract(NormalizedText(raw_text="我明天采购五常大米 80斤，供应商采无忧", normalized_text="我明天采购五常大米 80斤，供应商采无忧"))
    assert result.extractor_name == "llm"
    assert result.schedule_date_input == "明天"
    assert result.supplier_input == "采无忧"
    assert result.items[0].item_input_name == "五常大米"
    assert result.items[0].qty == 80
    assert result.items[0].uom == "斤"


def test_llm_extractor_rejects_invalid_json():
    class BrokenClient:
        def chat_json(self, *_args, **_kwargs):
            raise Exception("parse error")

    extractor = LlmMaterialRequestExtractor(llm_client=BrokenClient())
    result = extractor.extract(NormalizedText(raw_text="x", normalized_text="x"))
    assert any("LLM extraction failed" in w for w in result.warnings)


def test_llm_extractor_does_not_accept_negative_qty():
    extractor = LlmMaterialRequestExtractor(
        llm_client=DummyClient({
            "intent": "create_material_request", "confidence": 0.7, "schedule_date_input": "明天", "supplier_input": None,
            "warehouse_input": None, "items": [{"item_input_name": "五常大米", "qty": -1, "uom": "斤", "evidence": ""}], "missing_fields": [], "warnings": []
        })
    )
    result = extractor.extract(NormalizedText(raw_text="x", normalized_text="x"))
    assert result.items == []
    assert any("LLM extraction failed" in w for w in result.warnings)


def test_llm_extractor_missing_qty():
    extractor = LlmMaterialRequestExtractor(
        llm_client=DummyClient({
            "intent": "create_material_request", "confidence": 0.7, "schedule_date_input": "明天", "supplier_input": None,
            "warehouse_input": None, "items": [{"item_input_name": "五常大米", "qty": None, "uom": "斤", "evidence": ""}], "missing_fields": [], "warnings": []
        })
    )
    result = extractor.extract(NormalizedText(raw_text="x", normalized_text="x"))
    assert result.items == []
    assert any("missing_field:qty:五常大米" == w for w in result.warnings)


def test_llm_client_does_not_expose_api_key_on_error(monkeypatch):
    monkeypatch.setattr('app.config.settings.llm_api_key', 'super-secret-key')

    def _raise(*args, **kwargs):
        raise requests.RequestException('boom with super-secret-key')

    monkeypatch.setattr('requests.post', _raise)
    client = LlmClient()
    with pytest.raises(LlmRequestError) as exc_info:
        client.chat_json('s', 'u')
    assert 'super-secret-key' not in str(exc_info.value)

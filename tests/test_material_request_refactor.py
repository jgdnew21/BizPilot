from app.api.purchase.material_request_routes import prepare
from app.schemas.purchase.material_request import MaterialRequestPrepareRequest
from app.services.extractors.material_request_rule_extractor import RuleBasedMaterialRequestExtractor
from app.services.text_normalizer import TextNormalizer


def test_text_normalizer_keeps_raw_text():
    text = "我明天要采购五常大米 888 斤，供应商是 采无忧"
    normalized = TextNormalizer().normalize(text)
    assert normalized.raw_text == text
    assert normalized.normalized_text


def test_rule_extractor_basic_item():
    text = "明天要买五常大米80斤，供应商采无忧，入南宁仓"
    normalized = TextNormalizer().normalize(text)
    res = RuleBasedMaterialRequestExtractor().extract(normalized)
    assert res.schedule_date_input == "明天"
    assert res.supplier_input == "采无忧"
    assert res.warehouse_input == "南宁仓"
    assert len(res.items) == 1
    assert res.items[0].item_input_name == "五常大米"
    assert res.items[0].qty == 80
    assert res.items[0].uom == "斤"


def test_prepare_still_works_after_refactor():
    req = MaterialRequestPrepareRequest(
        session_id="wechat_group_001",
        user_id="u_001",
        user_name="店长张三",
        text="明天要买五常大米80斤，供应商采无忧，入南宁仓",
    )
    data = prepare(req)
    assert data["status"] == "pending_confirmation"
    assert "采购需求计划（待确认）" in data["markdown_text"]


def test_workflow_does_not_build_markdown_in_route():
    route_file = open("app/api/purchase/material_request_routes.py", "r", encoding="utf-8").read()
    assert "MarkdownService" not in route_file
    assert "prepare(req" in route_file

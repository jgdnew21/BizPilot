from app.api.purchase.purchase_request_routes import confirm, prepare
from app.schemas.purchase.material_request import MaterialRequestConfirmRequest, MaterialRequestPrepareRequest


def test_purchase_request_prepare_alias_returns_material_request_shape(monkeypatch):
    monkeypatch.setattr(
        "app.api.purchase.purchase_request_routes._workflow",
        lambda: type("W", (), {"prepare": lambda self, *args, **kwargs: {
            "snapshot_id": "snap_1",
            "doc_type": "material_request",
            "status": "ready_for_confirmation",
            "markdown_text": "ok",
        }})(),
    )
    res = prepare(MaterialRequestPrepareRequest(session_id="s1", user_id="u1", user_name="n", text="明天采购鸡蛋"))
    assert res["doc_type"] == "material_request"


def test_purchase_request_confirm_alias_calls_workflow(monkeypatch):
    monkeypatch.setattr(
        "app.api.purchase.purchase_request_routes._workflow",
        lambda: type("W", (), {"confirm": lambda self, *args, **kwargs: {
            "snapshot_id": "snap_1",
            "doc_type": "material_request",
            "status": "submitted",
            "erpnext_doc_no": "MAT-MR-2026-00001",
            "message": "ok",
            "error_code": None,
        }})(),
    )
    res = confirm(MaterialRequestConfirmRequest(session_id="s1", user_id="u1", snapshot_id="snap_1", confirm_text="确认采购需求"))
    assert res["status"] == "submitted"

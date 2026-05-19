from app.config import settings
from app.integrations.erpnext_client import ErpnextApiError, ErpnextClient
from app.repositories.master_data_cache_repository import MasterDataCacheRepository
from app.repositories.snapshot_repository import SnapshotRepository
from app.schemas.purchase.purchase_inbound import PurchaseInboundConfirmRequest, PurchaseInboundPrepareRequest
from app.services.master_data_match_service import MasterDataMatchService
from app.services.snapshot_service import SnapshotService
from app.workflows.purchase.purchase_inbound_workflow import PurchaseInboundWorkflow


def _wf():
    return PurchaseInboundWorkflow(
        match_service=MasterDataMatchService(MasterDataCacheRepository(settings.master_data_cache_db)),
        snapshot_service=SnapshotService(SnapshotRepository(settings.snapshot_dir)),
        erpnext_client=ErpnextClient(settings.erpnext_base_url, "k", "s"),
    )


def _prepare_snapshot(wf: PurchaseInboundWorkflow):
    req = PurchaseInboundPrepareRequest(
        session_id="test-session-001",
        user_id="u001",
        user_name="张三",
        source_channel="wechat",
        source_type="text",
        text="鲜鸡蛋90斤4.66 419.4 合计419.4",
        supplier_name="市场采购供应商",
        warehouse="南宁仓",
    )
    return wf.prepare(req)["snapshot_id"]


def test_confirm_creates_purchase_receipt_draft(monkeypatch):
    monkeypatch.setattr(ErpnextClient, "create_purchase_receipt", lambda self, payload: "MAT-PRE-2026-00001")
    wf = _wf()
    sid = _prepare_snapshot(wf)
    res = wf.confirm(PurchaseInboundConfirmRequest(session_id="test-session-001", user_id="u001", confirm_text="确认入库", snapshot_id=sid))
    assert res["status"] == "erp_draft_created"
    assert res["erp_purchase_receipt_name"] == "MAT-PRE-2026-00001"
    snap = wf.snapshot_service.get(sid)
    assert snap.status == "erp_draft_created"


def test_confirm_uses_snapshot_structured_payload_only(monkeypatch):
    captured = {}
    def _fake(self, payload):
        captured["payload"] = payload
        return "MAT-PRE-2026-00002"

    monkeypatch.setattr(ErpnextClient, "create_purchase_receipt", _fake)
    wf = _wf()
    sid = _prepare_snapshot(wf)
    snap = wf.snapshot_service.get(sid)
    expected_item_code = snap.structured_payload["items"][0]["item_code"]
    snap.raw_text = "改成苹果手机100台"
    wf.snapshot_service.update(snap)
    res = wf.confirm(PurchaseInboundConfirmRequest(session_id="test-session-001", user_id="u001", confirm_text="确认入库", snapshot_id=sid))
    assert res["status"] == "erp_draft_created"
    assert captured["payload"]["items"][0]["item_code"] == expected_item_code


def test_confirm_is_idempotent(monkeypatch):
    calls = {"n": 0}
    def _fake(self, payload):
        calls["n"] += 1
        return "MAT-PRE-2026-00003"

    monkeypatch.setattr(ErpnextClient, "create_purchase_receipt", _fake)
    wf = _wf()
    sid = _prepare_snapshot(wf)
    req = PurchaseInboundConfirmRequest(session_id="test-session-001", user_id="u001", confirm_text="确认入库", snapshot_id=sid)
    first = wf.confirm(req)
    second = wf.confirm(req)
    assert first["status"] == "erp_draft_created"
    assert second["status"] == "erp_draft_created"
    assert second["erp_purchase_receipt_name"] == "MAT-PRE-2026-00003"
    assert calls["n"] == 1


def test_confirm_blocks_invalid_status(monkeypatch):
    monkeypatch.setattr(ErpnextClient, "create_purchase_receipt", lambda self, payload: "x")
    wf = _wf()
    sid = _prepare_snapshot(wf)
    snap = wf.snapshot_service.get(sid)
    snap.status = "needs_user_fix"
    wf.snapshot_service.update(snap)
    res = wf.confirm(PurchaseInboundConfirmRequest(session_id="test-session-001", user_id="u001", confirm_text="确认入库", snapshot_id=sid))
    assert res["status"] == "invalid_snapshot_status"


def test_confirm_sets_erp_create_failed_on_api_error(monkeypatch):
    def _raise(self, payload):
        raise ErpnextApiError(417, "http://erp", "supplier missing")

    monkeypatch.setattr(ErpnextClient, "create_purchase_receipt", _raise)
    wf = _wf()
    sid = _prepare_snapshot(wf)
    res = wf.confirm(PurchaseInboundConfirmRequest(session_id="test-session-001", user_id="u001", confirm_text="确认入库", snapshot_id=sid))
    assert res["status"] == "erp_create_failed"
    snap = wf.snapshot_service.get(sid)
    assert snap.status == "erp_create_failed"

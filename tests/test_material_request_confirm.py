from app.config import settings
from app.integrations.erpnext_client import ErpnextClient
from app.repositories.master_data_repository import MasterDataRepository
from app.repositories.snapshot_repository import SnapshotRepository
from app.services.extractors.material_request_llm_extractor import LlmMaterialRequestExtractor
from app.services.extractors.material_request_rule_extractor import RuleBasedMaterialRequestExtractor
from app.services.master_data_service import MasterDataService
from app.services.snapshot_service import SnapshotService
from app.workflows.purchase.material_request_workflow import MaterialRequestWorkflow


def _wf():
    return MaterialRequestWorkflow(
        MasterDataService(MasterDataRepository(settings.master_data_dir)),
        SnapshotService(SnapshotRepository(settings.snapshot_dir)),
        ErpnextClient(settings.erpnext_base_url, 'k', 's'),
    )


def test_material_request_confirm_success_with_mock_erpnext(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'MAT-MR-2026-00001')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '后天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['status'] == 'submitted'


def test_invalid_confirm_text(monkeypatch):
    called = {'v': False}
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: called.__setitem__('v', True))
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '后天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, 'ok')
    assert res['error_code'] == 'INVALID_CONFIRM_TEXT'
    assert called['v'] is False


def test_confirm_does_not_call_llm(monkeypatch):
    monkeypatch.setattr(LlmMaterialRequestExtractor, 'extract', lambda self, text: (_ for _ in ()).throw(AssertionError('llm should not be called')))
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'MAT-MR-2026-00005')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    assert wf.confirm('wechat_group_001', 'u_001', sid, '确认')['status'] == 'submitted'


def test_confirm_does_not_call_rule_extractor(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'MAT-MR-2026-00006')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    monkeypatch.setattr(RuleBasedMaterialRequestExtractor, 'extract', lambda self, text: (_ for _ in ()).throw(AssertionError('rule extractor should not be called')))
    assert wf.confirm('wechat_group_001', 'u_001', sid, '确认')['status'] == 'submitted'


def test_confirm_uses_snapshot_structured_payload(monkeypatch):
    captured = {}
    def _fake(self, payload):
        captured['payload'] = payload
        return 'MAT-MR-2026-00007'
    monkeypatch.setattr(ErpnextClient, 'create_material_request', _fake)
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    snap = wf.snapshot_service.get(sid)
    snap.raw_text = '改成苹果手机100台，供应商任意，仓库任意'
    wf.snapshot_service.update(snap)
    expected_code = snap.structured_payload['items'][0]['matched_item']['item_code']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['status'] == 'submitted'
    assert captured['payload']['items'][0]['item_code'] == expected_code


def test_confirm_blocks_needs_clarification(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'x')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '帮我补点货')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['error_code'] == 'INCOMPLETE_DRAFT'


def test_confirm_blocks_blocked(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'x')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商不存在供应商，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['error_code'] == 'BLOCKED_DRAFT'


def test_confirm_blocks_superseded(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'x')
    wf = _wf()
    old_sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    wf.prepare('wechat_group_001', 'u_001', '店长张三', '数量改成100斤', previous_snapshot_id=old_sid)
    res = wf.confirm('wechat_group_001', 'u_001', old_sid, '确认')
    assert res['error_code'] == 'SNAPSHOT_SUPERSEDED'


def test_confirm_blocks_duplicate_submitted(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'MAT-MR-2026-00002')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    assert wf.confirm('wechat_group_001', 'u_001', sid, '确认')['status'] == 'submitted'
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['error_code'] == 'SNAPSHOT_ALREADY_SUBMITTED'


def test_confirm_requires_items(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'x')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    snap = wf.snapshot_service.get(sid)
    snap.structured_payload['items'] = []
    wf.snapshot_service.update(snap)
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['error_code'] == 'INCOMPLETE_DRAFT'


def test_confirm_requires_supplier_matched(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'x')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    snap = wf.snapshot_service.get(sid)
    snap.structured_payload['supplier']['status'] = 'unmatched'
    wf.snapshot_service.update(snap)
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['error_code'] == 'BLOCKED_DRAFT'


def test_confirm_requires_warehouse_matched(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'x')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    snap = wf.snapshot_service.get(sid)
    snap.structured_payload['warehouse']['status'] = 'unmatched'
    wf.snapshot_service.update(snap)
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['error_code'] == 'BLOCKED_DRAFT'


def test_confirm_payload_contains_warehouse_for_each_item(monkeypatch):
    captured = {}
    def _fake(self, payload):
        captured['payload'] = payload
        return 'MAT-MR-2026-00008'
    monkeypatch.setattr(ErpnextClient, 'create_material_request', _fake)
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['status'] == 'submitted'
    assert all(item['warehouse'] for item in captured['payload']['items'])


def test_confirm_success_updates_snapshot_submitted(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'MAT-MR-2026-00009')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    snap = wf.snapshot_service.get(sid)
    assert snap.status == 'submitted'
    assert snap.erpnext_doc_no == 'MAT-MR-2026-00009'


def test_erpnext_error_includes_response_body_summary(monkeypatch):
    from app.integrations.erpnext_client import ErpnextApiError

    def _raise(self, payload):
        raise ErpnextApiError(417, "http://erp.local/api/resource/Material Request", "{\"exc_type\":\"ValidationError\",\"message\":\"bad request\"}")

    monkeypatch.setattr(ErpnextClient, 'create_material_request', _raise)
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['status'] == 'submit_failed'
    assert 'ValidationError' in res['message']
    snap = wf.snapshot_service.get(sid)
    assert snap.status == 'submit_failed'
    assert 'ValidationError' in (snap.error_message or '')


def test_confirm_failure_message_says_material_request_not_purchase_order(monkeypatch):
    from app.integrations.erpnext_client import ErpnextApiError

    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: (_ for _ in ()).throw(
        ErpnextApiError(417, 'http://erp.local/api/resource/Material Request', 'error body')
    ))
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert '采购需求计划' in res['message']
    assert '采购订单' not in res['message']

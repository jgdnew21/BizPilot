from app.config import settings
from app.integrations.erpnext_client import ErpnextClient
from app.repositories.master_data_repository import MasterDataRepository
from app.repositories.snapshot_repository import SnapshotRepository
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
    def _fake(self, payload):
        called['v'] = True
        return 'x'
    monkeypatch.setattr(ErpnextClient, 'create_material_request', _fake)
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '后天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, 'ok')
    assert res['error_code'] == 'INVALID_CONFIRM_TEXT'
    assert called['v'] is False


def test_unmatched_item_blocks_submit(monkeypatch):
    called = {'v': False}
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: called.__setitem__('v', True))
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买火星米5斤，供应商采无忧，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['error_code'] == 'BLOCKED_DRAFT'
    assert called['v'] is False


def test_empty_items_blocks_submit(monkeypatch):
    called = {'v': False}
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: called.__setitem__('v', True))
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天采购，供应商采无忧，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['error_code'] == 'INCOMPLETE_DRAFT'
    assert called['v'] is False


def test_empty_items_markdown_does_not_ask_for_confirm():
    wf = _wf()
    res = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天采购，供应商采无忧，入南宁仓')
    assert '请回复 **“确认”** 提交采购需求计划' not in res['markdown_text']
    assert '采购需求计划（需补充）' in res['markdown_text']


def test_unmatched_supplier_blocks_confirm(monkeypatch):
    called = {'v': False}
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: called.__setitem__('v', True))
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天买五常大米80斤，供应商是不存在供应商，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['error_code'] == 'BLOCKED_DRAFT'
    assert called['v'] is False


def test_confirm_blocks_needs_clarification(monkeypatch):
    called = {'v': False}
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: called.__setitem__('v', True))
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '帮我补点货')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['error_code'] == 'INCOMPLETE_DRAFT'
    assert called['v'] is False


def test_confirm_blocks_blocked(monkeypatch):
    called = {'v': False}
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: called.__setitem__('v', True))
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商不存在供应商，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['error_code'] == 'BLOCKED_DRAFT'
    assert called['v'] is False


def test_confirm_allows_ready_for_confirmation(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'MAT-MR-2026-00002')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧，入南宁仓')['snapshot_id']
    res = wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert res['status'] == 'submitted'

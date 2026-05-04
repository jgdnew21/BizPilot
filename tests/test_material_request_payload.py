import json
from pathlib import Path

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


def test_confirm_does_not_reparse_raw_text(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: 'MAT-MR-2026-00001')
    wf = _wf()
    prep = wf.prepare('wechat_group_001', 'u_001', '店长张三', '今天要买五常大米80斤，供应商采无忧，入南宁仓')
    path = Path(settings.snapshot_dir) / f"{prep['snapshot_id']}.json"
    content = json.loads(path.read_text(encoding='utf-8'))
    content['raw_text'] = '改成未知商品'
    path.write_text(json.dumps(content, ensure_ascii=False), encoding='utf-8')
    res = wf.confirm('wechat_group_001', 'u_001', prep['snapshot_id'], '确认')
    assert res['status'] == 'submitted'


def test_mr_payload_contains_warehouse_on_each_item(monkeypatch):
    captured = {}
    monkeypatch.setattr(ErpnextClient, 'create_material_request', lambda self, payload: captured.setdefault('payload', payload) or 'MAT-MR-2026-00001')
    wf = _wf()
    sid = wf.prepare('wechat_group_001', 'u_001', '店长张三', '今天要买五常大米80斤，嘉木东来寿眉白茶10盒，供应商采无忧，入南宁仓')['snapshot_id']
    wf.confirm('wechat_group_001', 'u_001', sid, '确认')
    assert all('warehouse' in row for row in captured['payload']['items'])

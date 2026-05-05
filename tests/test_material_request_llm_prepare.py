from app.config import settings
from app.integrations.erpnext_client import ErpnextClient
from app.repositories.master_data_repository import MasterDataRepository
from app.repositories.snapshot_repository import SnapshotRepository
from app.services.master_data_service import MasterDataService
from app.services.snapshot_service import SnapshotService
from app.workflows.purchase.material_request_workflow import MaterialRequestWorkflow
from app.domain.extraction import ExtractionResult
from app.domain.purchase.material_request import PurchaseLineInput


def _wf():
    return MaterialRequestWorkflow(
        MasterDataService(MasterDataRepository(settings.master_data_dir)),
        SnapshotService(SnapshotRepository(settings.snapshot_dir)),
        ErpnextClient(settings.erpnext_base_url, 'k', 's'),
    )


def test_prepare_snapshot_records_extractor_name(monkeypatch):
    monkeypatch.setattr('app.config.settings.enable_llm_extractor', True)
    wf = _wf()
    monkeypatch.setattr(wf.extractor, 'extract', lambda _: ExtractionResult(
        raw_text='x', normalized_text='x', extractor_name='llm', supplier_input='采无忧',
        schedule_date_input='明天', warehouse_input='南宁仓',
        items=[PurchaseLineInput(item_input_name='五常大米', qty=80, uom='斤')], confidence=0.92
    ))

    res = wf.prepare('wechat_group_001', 'u_001', '店长张三', '我明天采购五常大米 80斤，供应商采无忧')
    snap = wf.snapshot_service.get(res['snapshot_id'])
    assert snap is not None
    assert snap.structured_payload['extractor_name'] == 'llm'
    assert snap.structured_payload['confidence'] == 0.92


def test_prepare_with_llm_success_returns_markdown(monkeypatch):
    monkeypatch.setattr('app.config.settings.enable_llm_extractor', True)
    wf = _wf()
    monkeypatch.setattr(wf.extractor, 'extract', lambda _: ExtractionResult(
        raw_text='x', normalized_text='x', extractor_name='llm', supplier_input='采无忧',
        schedule_date_input='明天', warehouse_input='南宁仓',
        items=[PurchaseLineInput(item_input_name='五常大米', qty=80, uom='斤')]
    ))

    res = wf.prepare('wechat_group_001', 'u_001', '店长张三', '我明天采购五常大米 80斤，供应商采无忧')
    assert '五常大米' in res['markdown_text']
    assert '80' in res['markdown_text']
    assert '采无忧 → 采无忧供货有限公司' in res['markdown_text']


def test_prepare_with_llm_missing_qty_needs_clarification(monkeypatch):
    monkeypatch.setattr('app.config.settings.enable_llm_extractor', True)
    wf = _wf()
    monkeypatch.setattr(wf.extractor, 'extract', lambda _: ExtractionResult(
        raw_text='x', normalized_text='x', extractor_name='llm', supplier_input='采无忧',
        schedule_date_input='明天', warehouse_input='南宁仓', items=[]
    ))

    res = wf.prepare('wechat_group_001', 'u_001', '店长张三', '我明天采购五常大米，供应商采无忧')
    assert res['status'] == 'needs_clarification'
    assert '请回复 **“确认”**' not in res['markdown_text']

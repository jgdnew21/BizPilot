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


def test_material_request_prepare_success():
    res = _wf().prepare('wechat_group_001', 'u_001', '店长张三', '后天要买五常大米80斤，嘉木东来寿眉白茶10盒，供应商采无忧，入南宁仓')
    assert res['snapshot_id']
    assert '采购需求计划（待确认）' in res['markdown_text']
    assert '采无忧供货有限公司' in res['markdown_text']
    assert '南宁仓 - 艾达D' in res['markdown_text']
    assert Path(settings.snapshot_dir, f"{res['snapshot_id']}.json").exists()


def test_parse_item_without_spaces():
    res = _wf().prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米80斤，供应商采无忧')
    assert '| 1 | 五常大米 | 80.0 | 斤 | 五常大米 | 已匹配 |' in res['markdown_text']


def test_parse_item_with_spaces():
    res = _wf().prepare('wechat_group_001', 'u_001', '店长张三', '我明天要采购五常大米 999 斤，供应商采无忧')
    assert '| 1 | 五常大米 | 999.0 | 斤 | 五常大米 | 已匹配 |' in res['markdown_text']


def test_parse_multiple_items_with_spaces():
    res = _wf().prepare('wechat_group_001', 'u_001', '店长张三', '明天要买五常大米 80 斤，嘉木东来寿眉白茶 10 盒，萌考拉冰淇淋 100 个，供应商采无忧，入南宁仓')
    assert '| 1 | 五常大米 | 80.0 | 斤 | 五常大米 | 已匹配 |' in res['markdown_text']
    assert '| 2 | 嘉木东来寿眉白茶 | 10.0 | 盒 | 嘉木东来寿眉白茶 | 已匹配 |' in res['markdown_text']
    assert '| 3 | 萌考拉冰淇淋 | 100.0 | 个 | 萌考拉冰淇淋 | 已匹配 |' in res['markdown_text']


def test_parse_supplier_without_connector():
    res = _wf().prepare('wechat_group_001', 'u_001', '店长张三', '明天买五常大米80斤，供应商采无忧')
    assert '- **供应商**：采无忧 → 采无忧供货有限公司' in res['markdown_text']


def test_parse_supplier_with_shi_no_space():
    res = _wf().prepare('wechat_group_001', 'u_001', '店长张三', '明天买五常大米80斤，供应商是采无忧')
    assert '- **供应商**：采无忧 → 采无忧供货有限公司' in res['markdown_text']


def test_parse_supplier_with_shi_and_space():
    res = _wf().prepare('wechat_group_001', 'u_001', '店长张三', '我明天要采购五常大米 888 斤，供应商是 采无忧')
    assert '- **供应商**：采无忧 → 采无忧供货有限公司' in res['markdown_text']


def test_parse_supplier_with_colon():
    res = _wf().prepare('wechat_group_001', 'u_001', '店长张三', '明天买五常大米80斤，供应商：采无忧')
    assert '- **供应商**：采无忧 → 采无忧供货有限公司' in res['markdown_text']


def test_parse_supplier_with_warehouse_after():
    res = _wf().prepare('wechat_group_001', 'u_001', '店长张三', '明天买五常大米80斤，供应商是 采无忧，入南宁仓')
    assert '- **供应商**：采无忧 → 采无忧供货有限公司' in res['markdown_text']
    assert '- **预计入库仓库**：南宁仓 → 南宁仓 - 艾达D' in res['markdown_text']


def test_unmatched_supplier_markdown_does_not_ask_confirm():
    res = _wf().prepare('wechat_group_001', 'u_001', '店长张三', '明天买五常大米80斤，供应商是不存在供应商')
    assert '请回复 **“确认”** 提交采购需求计划' not in res['markdown_text']
    assert '⚠️ 存在未匹配项，暂不能提交。' in res['markdown_text']

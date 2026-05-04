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

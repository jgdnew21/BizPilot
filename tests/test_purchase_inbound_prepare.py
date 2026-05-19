from pathlib import Path

from app.config import settings
from app.repositories.master_data_cache_repository import MasterDataCacheRepository
from app.repositories.snapshot_repository import SnapshotRepository
from app.schemas.purchase.purchase_inbound import PurchaseInboundPrepareRequest
from app.services.master_data_match_service import MasterDataMatchService
from app.services.snapshot_service import SnapshotService
from app.workflows.purchase.purchase_inbound_workflow import PurchaseInboundWorkflow


def make_workflow(tmp_path):
    repository = MasterDataCacheRepository(str(tmp_path / "master_data.sqlite3"))
    repository.upsert_items(
        [
            {
                "name": "ITEM-0001",
                "item_code": "ITEM-0001",
                "item_name": "鲜鸡蛋",
                "stock_uom": "斤",
                "disabled": 0,
            },
            {
                "name": "ITEM-0002",
                "item_code": "ITEM-0002",
                "item_name": "土鸡蛋",
                "stock_uom": "斤",
                "disabled": 0,
            },
            {
                "name": "ITEM-0003",
                "item_code": "ITEM-0003",
                "item_name": "红糖",
                "stock_uom": "包",
                "disabled": 0,
            },
        ]
    )
    repository.upsert_suppliers(
        [{"name": "市场采购供应商", "supplier_name": "市场采购供应商", "disabled": 0}]
    )
    repository.upsert_warehouses(
        [
            {
                "name": "仓库-华食泰",
                "warehouse_name": "仓库-华食泰",
                "disabled": 0,
                "is_group": 0,
            }
        ]
    )
    repository.upsert_uoms([{"name": "斤", "enabled": 1}, {"name": "包", "enabled": 1}])
    return PurchaseInboundWorkflow(
        MasterDataMatchService(repository),
        SnapshotService(SnapshotRepository(str(tmp_path / "snapshots"))),
    )


def make_request(**overrides):
    payload = {
        "session_id": "test-session-001",
        "user_id": "u001",
        "user_name": "测试用户",
        "source_channel": "wechat",
        "source_type": "text",
        "text": "鲜鸡蛋90斤 4.66元/斤，土鸡蛋35斤 5.14元/斤，共599.3元",
        "supplier_name": "市场采购供应商",
        "warehouse": "仓库-华食泰",
    }
    payload.update(overrides)
    return PurchaseInboundPrepareRequest(**payload)


def test_purchase_inbound_prepare_success_pending_confirmation(tmp_path):
    workflow = make_workflow(tmp_path)

    result = workflow.prepare(make_request())

    assert result["status"] == "pending_confirmation"
    assert result["snapshot_id"].startswith("pin_")
    assert result["validation"]["status"] == "passed"
    assert "采购入库确认单（待确认）" in result["markdown"]
    assert "| 1 | 鲜鸡蛋 | 鲜鸡蛋 | 90" in result["markdown"]
    assert "| 2 | 土鸡蛋 | 土鸡蛋 | 35" in result["markdown"]
    assert "回复“确认入库”" in result["markdown"]


def test_purchase_inbound_snapshot_saved(tmp_path):
    workflow = make_workflow(tmp_path)

    result = workflow.prepare(make_request())
    snapshot = workflow.snapshot_service.get(result["snapshot_id"])

    assert snapshot is not None
    assert snapshot.doc_type == "purchase_inbound"
    assert snapshot.status == "pending_confirmation"
    assert snapshot.structured_payload["items"][0]["item_code"] == "ITEM-0001"
    assert snapshot.markdown_text == result["markdown"]


def test_purchase_inbound_missing_supplier_uses_default(tmp_path):
    workflow = make_workflow(tmp_path)

    result = workflow.prepare(make_request(supplier_name=None))

    assert result["status"] == "pending_confirmation"
    snapshot = workflow.snapshot_service.get(result["snapshot_id"])
    assert (
        snapshot.structured_payload["supplier"]["erp_supplier_name"] == "市场采购供应商"
    )


def test_purchase_inbound_unknown_supplier_falls_back_to_default(tmp_path):
    workflow = make_workflow(tmp_path)

    result = workflow.prepare(make_request(supplier_name="不存在供应商"))

    assert result["status"] == "pending_confirmation"
    assert result["validation"]["warnings"][0]["type"] == "supplier_fallback_default"
    snapshot = workflow.snapshot_service.get(result["snapshot_id"])
    assert snapshot.raw_supplier_name == "不存在供应商"
    assert snapshot.erp_supplier_name == "市场采购供应商"


def test_purchase_inbound_item_not_found_needs_user_fix(tmp_path):
    workflow = make_workflow(tmp_path)

    result = workflow.prepare(make_request(text="不存在商品90斤 4.66元/斤，共419.4元"))

    assert result["status"] == "needs_user_fix"
    assert result["validation"]["errors"][0]["type"] == "item_not_found"
    assert "采购入库确认单（需修正）" in result["markdown"]
    assert "未匹配" in result["markdown"]


def test_purchase_inbound_ambiguous_item_needs_user_fix(tmp_path):
    workflow = make_workflow(tmp_path)

    result = workflow.prepare(make_request(text="鸡蛋90斤 4.66元/斤，共419.4元"))

    assert result["status"] == "needs_user_fix"
    assert any(
        error["type"] == "item_ambiguous" for error in result["validation"]["errors"]
    )
    assert "候选：鲜鸡蛋 / 土鸡蛋" in result["markdown"]
    assert "商品不明确" in result["markdown"]


def test_purchase_inbound_uom_not_found_needs_user_fix(tmp_path):
    workflow = make_workflow(tmp_path)

    result = workflow.prepare(make_request(text="鲜鸡蛋90箱 4.66元/箱，共419.4元"))

    assert result["status"] == "needs_user_fix"
    assert any(
        error["type"] == "uom_invalid" for error in result["validation"]["errors"]
    )
    assert "单位不存在于缓存" in result["markdown"]


def test_purchase_inbound_warehouse_not_found_needs_user_fix(tmp_path):
    workflow = make_workflow(tmp_path)

    result = workflow.prepare(make_request(warehouse="不存在仓库"))

    assert result["status"] == "needs_user_fix"
    assert any(
        error["type"] == "warehouse_invalid" for error in result["validation"]["errors"]
    )
    assert "仓库不存在于缓存" in result["markdown"]


def test_purchase_inbound_reported_total_mismatch_returns_warning(tmp_path):
    workflow = make_workflow(tmp_path)

    result = workflow.prepare(make_request(text="鲜鸡蛋90斤 4.66元/斤，共1元"))

    assert result["status"] == "pending_confirmation"
    assert result["validation"]["warnings"][0]["type"] == "reported_total_mismatch"
    assert "报单合计 1.00 与系统计算合计 419.40 不一致" in result["markdown"]


def test_purchase_inbound_api_route_uses_settings(tmp_path):
    old_db, old_snapshot_dir = settings.master_data_cache_db, settings.snapshot_dir
    settings.master_data_cache_db = str(tmp_path / "api_master_data.sqlite3")
    settings.snapshot_dir = str(tmp_path / "api_snapshots")
    repository = MasterDataCacheRepository(settings.master_data_cache_db)
    repository.upsert_items(
        [
            {
                "name": "ITEM-0001",
                "item_code": "ITEM-0001",
                "item_name": "鲜鸡蛋",
                "stock_uom": "斤",
                "disabled": 0,
            }
        ]
    )
    repository.upsert_suppliers(
        [{"name": "市场采购供应商", "supplier_name": "市场采购供应商", "disabled": 0}]
    )
    repository.upsert_warehouses(
        [
            {
                "name": "仓库-华食泰",
                "warehouse_name": "仓库-华食泰",
                "disabled": 0,
                "is_group": 0,
            }
        ]
    )
    repository.upsert_uoms([{"name": "斤", "enabled": 1}])
    try:
        from app.api.purchase.purchase_inbound_routes import prepare

        result = prepare(make_request(text="鲜鸡蛋90斤 4.66元/斤，共419.4元"))
    finally:
        settings.master_data_cache_db = old_db
        settings.snapshot_dir = old_snapshot_dir

    assert result["status"] == "pending_confirmation"
    assert Path(tmp_path / "api_snapshots" / f"{result['snapshot_id']}.json").exists()

from app.config import settings
from app.repositories.master_data_cache_repository import MasterDataCacheRepository
from app.services.master_data_match_service import MasterDataMatchService


def make_service(tmp_path):
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
                "item_name": "龙胜土鸡蛋",
                "stock_uom": "斤",
                "disabled": 0,
            },
            {
                "name": "ITEM-0004",
                "item_code": "ITEM-0004",
                "item_name": "鸭蛋",
                "stock_uom": "斤",
                "disabled": 1,
            },
            {
                "name": "ITEM-0005",
                "item_code": "ITEM-0005",
                "item_name": "红糖",
                "stock_uom": "包",
                "disabled": 0,
            },
        ]
    )
    repository.upsert_suppliers(
        [
            {"name": "SUP-0001", "supplier_name": "市场采购供应商", "disabled": 0},
            {"name": "SUP-0002", "supplier_name": "南宁市场", "disabled": 0},
        ]
    )
    repository.upsert_warehouses(
        [
            {
                "name": "WH-0001",
                "warehouse_name": "南宁仓 - 艾达D",
                "disabled": 0,
                "is_group": 0,
            }
        ]
    )
    repository.upsert_uoms(
        [
            {"name": "斤", "enabled": 1},
            {"name": "包", "enabled": 1},
        ]
    )
    return MasterDataMatchService(repository), repository


def test_item_name_exact_match(tmp_path):
    service, _ = make_service(tmp_path)

    result = service.match_item("鲜鸡蛋")

    assert result.status == "matched"
    assert result.selected["item_code"] == "ITEM-0001"
    assert result.message == "已精确匹配"


def test_item_code_exact_match(tmp_path):
    service, _ = make_service(tmp_path)

    result = service.match_item("ITEM-0001")

    assert result.status == "matched"
    assert result.selected["item_name"] == "鲜鸡蛋"


def test_fuzzy_match_unique_result(tmp_path):
    service, _ = make_service(tmp_path)

    result = service.match_item("红")

    assert result.status == "matched"
    assert result.selected["item_code"] == "ITEM-0005"
    assert "模糊" in result.message


def test_fuzzy_match_multiple_candidates_returns_ambiguous(tmp_path):
    service, _ = make_service(tmp_path)

    result = service.match_item("鸡蛋")

    assert result.status == "ambiguous"
    assert {candidate["item_code"] for candidate in result.candidates} >= {
        "ITEM-0001",
        "ITEM-0002",
        "ITEM-0003",
    }


def test_item_not_found_returns_not_found(tmp_path):
    service, _ = make_service(tmp_path)

    result = service.match_item("不存在商品")

    assert result.status == "not_found"


def test_disabled_item_cannot_auto_match(tmp_path):
    service, _ = make_service(tmp_path)

    result = service.match_item("鸭蛋")

    assert result.status == "disabled"
    assert result.selected["item_code"] == "ITEM-0004"


def test_missing_supplier_uses_default_supplier(tmp_path):
    service, _ = make_service(tmp_path)

    result = service.match_supplier(None, default_supplier="市场采购供应商")

    assert result.status == "matched"
    assert result.selected["raw_supplier_name"] is None
    assert result.selected["erp_supplier_name"] == "市场采购供应商"


def test_missing_default_supplier_returns_not_found(tmp_path):
    service, _ = make_service(tmp_path)

    result = service.match_supplier(None, default_supplier="不存在默认供应商")

    assert result.status == "not_found"
    assert result.message == "默认供应商不存在于缓存"


def test_warehouse_not_found_returns_validation_failed(tmp_path):
    service, _ = make_service(tmp_path)

    result = service.validate_warehouse("不存在仓库")

    assert result.status == "validation_failed"
    assert result.message == "仓库不存在于缓存"


def test_uom_not_found_returns_validation_failed(tmp_path):
    service, _ = make_service(tmp_path)

    result = service.validate_uom("箱")

    assert result.status == "validation_failed"
    assert result.message == "单位不存在于缓存"


def test_master_data_search_api_returns_items_and_suppliers(tmp_path):
    _, repository = make_service(tmp_path)
    old_db = settings.master_data_cache_db
    settings.master_data_cache_db = str(repository.db_path)
    try:
        from app.api.master_data import search_items, search_suppliers

        item_response = search_items(q="鲜鸡蛋", limit=20)
        supplier_response = search_suppliers(q="市场", limit=20)
    finally:
        settings.master_data_cache_db = old_db

    assert item_response["results"][0]["item_code"] == "ITEM-0001"
    assert supplier_response["results"][0]["supplier_name"] == "市场采购供应商"

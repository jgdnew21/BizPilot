from __future__ import annotations

from app.models.master_data_cache import ErpnextItemCache
from app.repositories.master_data_cache_repository import MasterDataCacheRepository
from app.services.master_data_sync_service import MasterDataSyncService


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], dict | None]] = []
        self.data = {
            "Item": [{"name": "ITEM-001", "item_code": "ITEM-001", "item_name": "苹果"}],
            "Supplier": [{"name": "SUP-001", "supplier_name": "供应商"}],
            "Warehouse": [{"name": "WH-001", "warehouse_name": "主仓"}],
            "UOM": [{"name": "个", "enabled": 1}],
        }

    def fetch_all(self, doctype, fields, filters=None):  # type: ignore[no-untyped-def]
        self.calls.append((doctype, fields, filters))
        return self.data[doctype]


def test_repository_upsert_is_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = MasterDataCacheRepository(f"sqlite:///{tmp_path}/cache.db")
    repo.init_schema()

    row = {"name": "ITEM-001", "item_code": "ITEM-001", "item_name": "苹果", "modified": "2026-01-01"}
    assert repo.upsert_items([row]) == 1
    assert repo.upsert_items([{**row, "item_name": "红苹果"}]) == 1

    assert repo.count(ErpnextItemCache) == 1
    item = repo.fetch_one_by_key("erpnext_item_cache", "item_code", "ITEM-001")
    assert item is not None
    assert item["item_name"] == "红苹果"
    assert "红苹果" in item["raw_json"]


def test_master_data_service_returns_summary(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = MasterDataCacheRepository(f"sqlite:///{tmp_path}/cache.db")
    service = MasterDataSyncService(client=FakeClient(), repository=repo)  # type: ignore[arg-type]

    summary = service.sync_master_data()

    assert summary == {
        "items": {"fetched": 1, "upserted": 1},
        "suppliers": {"fetched": 1, "upserted": 1},
        "warehouses": {"fetched": 1, "upserted": 1},
        "uoms": {"fetched": 1, "upserted": 1},
    }

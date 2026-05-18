from __future__ import annotations

from typing import Any, Callable

from app.core.config import ERPNEXT_COMPANY
from app.integrations.erpnext.client import ERPNextMasterDataClient
from app.repositories.master_data_cache_repository import MasterDataCacheRepository


ITEM_FIELDS = [
    "name",
    "item_code",
    "item_name",
    "item_group",
    "stock_uom",
    "disabled",
    "is_stock_item",
    "description",
    "modified",
]
SUPPLIER_FIELDS = ["name", "supplier_name", "supplier_group", "disabled", "modified"]
WAREHOUSE_FIELDS = ["name", "warehouse_name", "company", "is_group", "disabled", "modified"]
UOM_FIELDS = ["name", "enabled", "modified"]


class MasterDataSyncService:
    """Coordinates full ERPNext master-data sync into BizPilot's local cache."""

    def __init__(
        self,
        client: ERPNextMasterDataClient | None = None,
        repository: MasterDataCacheRepository | None = None,
    ) -> None:
        self.client = client or ERPNextMasterDataClient()
        self.repository = repository or MasterDataCacheRepository()
        self.repository.init_schema()

    def sync_master_data(self) -> dict[str, dict[str, int]]:
        return {
            "items": self.sync_items(),
            "suppliers": self.sync_suppliers(),
            "warehouses": self.sync_warehouses(),
            "uoms": self.sync_uoms(),
        }

    def sync_items(self) -> dict[str, int]:
        return self._sync_one("Item", ITEM_FIELDS, None, self.repository.upsert_items)

    def sync_suppliers(self) -> dict[str, int]:
        return self._sync_one("Supplier", SUPPLIER_FIELDS, None, self.repository.upsert_suppliers)

    def sync_warehouses(self) -> dict[str, int]:
        filters = {"company": ERPNEXT_COMPANY} if ERPNEXT_COMPANY else None
        return self._sync_one("Warehouse", WAREHOUSE_FIELDS, filters, self.repository.upsert_warehouses)

    def sync_uoms(self) -> dict[str, int]:
        return self._sync_one("UOM", UOM_FIELDS, None, self.repository.upsert_uoms)

    def _sync_one(
        self,
        doctype: str,
        fields: list[str],
        filters: dict[str, Any] | None,
        upsert: Callable[[list[dict[str, Any]]], int],
    ) -> dict[str, int]:
        rows = self.client.fetch_all(doctype=doctype, fields=fields, filters=filters)
        upserted = upsert(rows)
        return {"fetched": len(rows), "upserted": upserted}

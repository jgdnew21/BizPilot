"""Master data synchronization service.

This service performs full sync from ERPNext to local cache tables
(erpnext_items / erpnext_suppliers / erpnext_warehouses / erpnext_uoms).
Syncing master data does not create any ERP business documents.
"""
from typing import Any

from app.integrations.erpnext_client import ErpnextClient
from app.models.master_data_cache import (
    ITEM_MASTER_DATA,
    SUPPLIER_MASTER_DATA,
    UOM_MASTER_DATA,
    WAREHOUSE_MASTER_DATA,
    MasterDataDefinition,
    MasterDataSyncResult,
)
from app.repositories.master_data_cache_repository import MasterDataCacheRepository


class MasterDataSyncService:
    """Coordinates full ERPNext master-data sync into the local cache."""

    def __init__(self, client: ErpnextClient, repository: MasterDataCacheRepository, company: str | None = None):
        self.client = client
        self.repository = repository
        self.company = company

    def sync_all(self) -> dict[str, MasterDataSyncResult]:
        """Run full sync for all supported master data types."""
        return {
            "items": self.sync_items(),
            "suppliers": self.sync_suppliers(),
            "warehouses": self.sync_warehouses(),
            "uoms": self.sync_uoms(),
        }

    def sync_items(self) -> MasterDataSyncResult:
        rows = self._fetch(ITEM_MASTER_DATA)
        return MasterDataSyncResult(fetched=len(rows), upserted=self.repository.upsert_items(rows))

    def sync_suppliers(self) -> MasterDataSyncResult:
        rows = self._fetch(SUPPLIER_MASTER_DATA)
        return MasterDataSyncResult(fetched=len(rows), upserted=self.repository.upsert_suppliers(rows))

    def sync_warehouses(self) -> MasterDataSyncResult:
        filters: dict[str, Any] | None = {"company": self.company} if self.company else None
        rows = self._fetch(WAREHOUSE_MASTER_DATA, filters=filters)
        return MasterDataSyncResult(fetched=len(rows), upserted=self.repository.upsert_warehouses(rows))

    def sync_uoms(self) -> MasterDataSyncResult:
        rows = self._fetch(UOM_MASTER_DATA)
        return MasterDataSyncResult(fetched=len(rows), upserted=self.repository.upsert_uoms(rows))

    def _fetch(self, definition: MasterDataDefinition, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self.client.fetch_all(definition.doctype, definition.fields, filters=filters)

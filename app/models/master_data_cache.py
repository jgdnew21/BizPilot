from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MasterDataSyncResult:
    fetched: int
    upserted: int

    def to_dict(self) -> dict[str, int]:
        return {"fetched": self.fetched, "upserted": self.upserted}


@dataclass(frozen=True)
class MasterDataDefinition:
    summary_key: str
    doctype: str
    fields: list[str]


ITEM_MASTER_DATA = MasterDataDefinition(
    summary_key="items",
    doctype="Item",
    fields=[
        "name",
        "item_code",
        "item_name",
        "item_group",
        "stock_uom",
        "disabled",
        "is_stock_item",
        "description",
        "modified",
    ],
)

SUPPLIER_MASTER_DATA = MasterDataDefinition(
    summary_key="suppliers",
    doctype="Supplier",
    fields=["name", "supplier_name", "supplier_group", "disabled", "modified"],
)

WAREHOUSE_MASTER_DATA = MasterDataDefinition(
    summary_key="warehouses",
    doctype="Warehouse",
    fields=["name", "warehouse_name", "company", "is_group", "disabled", "modified"],
)

UOM_MASTER_DATA = MasterDataDefinition(
    summary_key="uoms",
    doctype="UOM",
    fields=["name", "enabled", "modified"],
)


def raw_json_value(row: dict[str, Any]) -> dict[str, Any]:
    """Return a plain dict copy suitable for JSON serialization."""
    return dict(row)

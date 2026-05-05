from __future__ import annotations

from typing import Any


def build_material_request_erpnext_payload(snapshot) -> dict[str, Any]:
    payload = snapshot.structured_payload or {}
    schedule_date = payload.get("schedule_date")
    items = payload.get("items") or []

    erp_items: list[dict[str, Any]] = []
    for row in items:
        matched_item = row.get("matched_item") or {}
        row_warehouse = row.get("warehouse") or (payload.get("warehouse") or {}).get("warehouse_standard_name")
        erp_items.append(
            {
                "item_code": matched_item.get("item_code"),
                "qty": row.get("qty"),
                "uom": row.get("uom"),
                "schedule_date": schedule_date,
                "warehouse": row_warehouse,
            }
        )

    return {
        "doctype": "Material Request",
        "material_request_type": "Purchase",
        "schedule_date": schedule_date,
        "items": erp_items,
    }

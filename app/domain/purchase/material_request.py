from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PurchaseLineInput(BaseModel):
    item_input_name: str
    qty: float
    uom: str


class MatchedItem(BaseModel):
    item_input_name: str
    item_code: str | None = None
    item_name: str | None = None
    item_name_snapshot: str | None = None
    purchase_uom: str | None = None
    status: Literal["matched", "unmatched"]


class MatchedSupplier(BaseModel):
    supplier_input: str | None = None
    supplier_standard_name: str | None = None
    status: Literal["matched", "unmatched"]


class MatchedWarehouse(BaseModel):
    warehouse_input: str | None = None
    warehouse_standard_name: str | None = None
    status: Literal["matched", "unmatched"]


class MaterialRequestDraft(BaseModel):
    doc_type: Literal["material_request"] = "material_request"
    session_id: str
    user_id: str
    user_name: str
    raw_text: str
    schedule_date: str
    schedule_date_input: str
    supplier: MatchedSupplier
    warehouse: MatchedWarehouse
    items: list[dict[str, Any]]
    markdown_text: str = ""
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class PurchaseSnapshot(BaseModel):
    snapshot_id: str
    doc_type: str
    session_id: str
    user_id: str
    status: Literal[
        "ready_for_confirmation",
        "needs_clarification",
        "blocked",
        "superseded",
        "pending_confirmation",
        "confirmed",
        "submitted",
        "submit_failed",
        "invalid",
    ]
    raw_text: str
    markdown_text: str
    structured_payload: dict[str, Any]
    previous_snapshot_id: str | None = None
    revision: int = 1
    erpnext_doc_no: str | None = None
    error_message: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    confirmed_at: str | None = None
    submitted_at: str | None = None

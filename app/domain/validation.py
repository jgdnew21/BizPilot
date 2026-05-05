from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    status: Literal["ready_for_confirmation", "needs_clarification", "blocked"]
    missing_fields: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    can_confirm: bool


class BusinessValidator:
    @staticmethod
    def validate_material_request_payload(payload: dict[str, Any]) -> ValidationResult:
        missing_fields: list[str] = []
        blocking_reasons: list[str] = []

        supplier = payload.get("supplier") or {}
        warehouse = payload.get("warehouse") or {}
        items = payload.get("items") or []
        schedule_date_status = payload.get("schedule_date_status")
        schedule_date_message = payload.get("schedule_date_message") or ""

        if not supplier.get("supplier_input"):
            missing_fields.append("supplier")
        if not warehouse.get("warehouse_input"):
            missing_fields.append("warehouse")
        if not items:
            missing_fields.append("items")
        if schedule_date_status == "unparsed":
            missing_fields.append("schedule_date")
        if "parsed_date_is_in_past" in schedule_date_message:
            missing_fields.append("schedule_date_past")

        if supplier.get("status") != "matched":
            blocking_reasons.append("supplier_unmatched")
        if warehouse.get("status") != "matched":
            blocking_reasons.append("warehouse_unmatched")

        for row in items:
            matched_item = row.get("matched_item") or {}
            if matched_item.get("status") != "matched":
                blocking_reasons.append("item_unmatched")
                break
            if row.get("uom") != matched_item.get("purchase_uom"):
                blocking_reasons.append("uom_mismatch")
                break

        if missing_fields:
            return ValidationResult(
                status="needs_clarification",
                missing_fields=missing_fields,
                blocking_reasons=blocking_reasons,
                can_confirm=False,
            )
        if blocking_reasons:
            return ValidationResult(
                status="blocked",
                missing_fields=missing_fields,
                blocking_reasons=blocking_reasons,
                can_confirm=False,
            )
        return ValidationResult(
            status="ready_for_confirmation",
            missing_fields=missing_fields,
            blocking_reasons=blocking_reasons,
            can_confirm=True,
        )

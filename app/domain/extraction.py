from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.purchase.material_request import PurchaseLineInput


class NormalizedText(BaseModel):
    raw_text: str
    normalized_text: str


class ExtractionResult(BaseModel):
    raw_text: str
    normalized_text: str
    intent: str | None = None
    confidence: float | None = None
    schedule_date_input: str | None = None
    supplier_input: str | None = None
    warehouse_input: str | None = None
    items: list[PurchaseLineInput] = Field(default_factory=list)
    extractor_name: str = "rule_based"
    warnings: list[str] = Field(default_factory=list)

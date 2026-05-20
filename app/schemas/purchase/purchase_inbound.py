from pydantic import BaseModel, Field


class PurchaseInboundPrepareRequest(BaseModel):
    session_id: str
    user_id: str
    user_name: str
    source_channel: str = "wechat"
    source_type: str = "text"
    text: str | None = None
    raw_text: str | None = None
    supplier_name: str | None = None
    warehouse: str | None = None

    def get_input_text(self) -> str:
        return (self.text or self.raw_text or "").strip()


class ValidationIssue(BaseModel):
    type: str
    message: str
    line_no: int | None = None


class PurchaseInboundValidation(BaseModel):
    status: str
    warnings: list[ValidationIssue] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)


class PurchaseInboundPrepareResponse(BaseModel):
    status: str
    snapshot_id: str
    markdown: str
    validation: PurchaseInboundValidation


class PurchaseInboundConfirmRequest(BaseModel):
    session_id: str
    user_id: str
    confirm_text: str
    snapshot_id: str | None = None


class PurchaseInboundConfirmResponse(BaseModel):
    status: str
    snapshot_id: str
    erp_purchase_receipt_name: str | None = None
    message: str
    error_detail: str | None = None

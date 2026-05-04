from pydantic import BaseModel


class MaterialRequestPrepareRequest(BaseModel):
    session_id: str
    user_id: str
    user_name: str
    text: str


class MaterialRequestPrepareResponse(BaseModel):
    snapshot_id: str
    doc_type: str
    status: str
    markdown_text: str


class MaterialRequestConfirmRequest(BaseModel):
    session_id: str
    user_id: str
    snapshot_id: str
    confirm_text: str


class MaterialRequestConfirmResponse(BaseModel):
    snapshot_id: str
    doc_type: str
    status: str
    erpnext_doc_no: str | None
    message: str
    error_code: str | None = None

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    status: str
    message: str
    snapshot_id: str | None = None
    error_code: str | None = None

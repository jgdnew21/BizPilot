from fastapi import APIRouter, HTTPException

from app.api.purchase.material_request_routes import _workflow
from app.schemas.purchase.material_request import (
    MaterialRequestConfirmRequest,
    MaterialRequestConfirmResponse,
    MaterialRequestPrepareRequest,
    MaterialRequestPrepareResponse,
)

router = APIRouter(prefix="/api/purchase/request", tags=["purchase-request"])


@router.post("/prepare", response_model=MaterialRequestPrepareResponse)
def prepare(req: MaterialRequestPrepareRequest):
    try:
        return _workflow().prepare(req.session_id, req.user_id, req.user_name, req.text, req.previous_snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/confirm", response_model=MaterialRequestConfirmResponse)
def confirm(req: MaterialRequestConfirmRequest):
    return _workflow().confirm(req.session_id, req.user_id, req.snapshot_id, req.confirm_text)

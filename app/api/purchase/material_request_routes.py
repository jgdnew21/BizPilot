from fastapi import APIRouter, HTTPException

from app.config import settings
from app.integrations.erpnext_client import ErpnextClient
from app.repositories.master_data_repository import MasterDataRepository
from app.repositories.snapshot_repository import SnapshotRepository
from app.schemas.purchase.material_request import (
    MaterialRequestConfirmRequest,
    MaterialRequestConfirmResponse,
    MaterialRequestPrepareRequest,
    MaterialRequestPrepareResponse,
)
from app.services.master_data_service import MasterDataService
from app.services.snapshot_service import SnapshotService
from app.workflows.purchase.material_request_workflow import MaterialRequestWorkflow

router = APIRouter(prefix="/api/purchase/material-requests", tags=["material-requests"])


def _workflow() -> MaterialRequestWorkflow:
    return MaterialRequestWorkflow(
        master_data_service=MasterDataService(MasterDataRepository(settings.master_data_dir)),
        snapshot_service=SnapshotService(SnapshotRepository(settings.snapshot_dir)),
        erpnext_client=ErpnextClient(settings.erpnext_base_url, settings.erpnext_api_key, settings.erpnext_api_secret),
    )


@router.post("/prepare", response_model=MaterialRequestPrepareResponse)
def prepare(req: MaterialRequestPrepareRequest):
    try:
        return _workflow().prepare(req.session_id, req.user_id, req.user_name, req.text, req.previous_snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/confirm", response_model=MaterialRequestConfirmResponse)
def confirm(req: MaterialRequestConfirmRequest):
    return _workflow().confirm(req.session_id, req.user_id, req.snapshot_id, req.confirm_text)

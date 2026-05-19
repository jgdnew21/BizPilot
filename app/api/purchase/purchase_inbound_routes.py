from fastapi import APIRouter

from app.schemas.purchase.purchase_inbound import (
    PurchaseInboundConfirmRequest,
    PurchaseInboundConfirmResponse,
    PurchaseInboundPrepareRequest,
    PurchaseInboundPrepareResponse,
)
from app.workflows.purchase.purchase_inbound_workflow import PurchaseInboundWorkflow

router = APIRouter(prefix="/api/purchase/inbound", tags=["purchase-inbound"])


@router.post("/prepare", response_model=PurchaseInboundPrepareResponse)
def prepare(req: PurchaseInboundPrepareRequest):
    return PurchaseInboundWorkflow.from_settings().prepare(req)


@router.post("/confirm", response_model=PurchaseInboundConfirmResponse)
def confirm(req: PurchaseInboundConfirmRequest):
    return PurchaseInboundWorkflow.from_settings().confirm(req)

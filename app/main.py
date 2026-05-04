from fastapi import FastAPI

from app.api.purchase.material_request_routes import router as mr_router
from app.api.purchase.purchase_order_routes import router as po_router
from app.api.purchase.purchase_receipt_routes import router as pr_router

app = FastAPI(title="BizPilot v0.2")
app.include_router(mr_router)
app.include_router(po_router)
app.include_router(pr_router)

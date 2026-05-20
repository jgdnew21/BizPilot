"""BizPilot FastAPI app entrypoint.

Registers both purchase chains:
- material request (pre-purchase)
- purchase inbound (post-purchase receipt draft)
plus master-data sync/search routes.
"""
from fastapi import FastAPI

from app.api.erpnext_sync import router as erpnext_sync_router
from app.api.health_routes import router as health_router
from app.api.master_data import router as master_data_router
from app.api.purchase.material_request_routes import router as mr_router
from app.api.purchase.purchase_order_routes import router as po_router
from app.api.purchase.purchase_receipt_routes import router as pr_router
from app.api.purchase.purchase_inbound_routes import router as inbound_router
from app.api.purchase.purchase_request_routes import router as purchase_request_router

app = FastAPI(title="BizPilot v0.2")
app.include_router(mr_router)
app.include_router(po_router)
app.include_router(pr_router)
app.include_router(inbound_router)
app.include_router(purchase_request_router)
app.include_router(erpnext_sync_router)
app.include_router(master_data_router)

app.include_router(health_router)

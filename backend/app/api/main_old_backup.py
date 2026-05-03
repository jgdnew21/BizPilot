from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from sqlalchemy import create_engine, text
from datetime import datetime
import uuid


app = FastAPI(title="BizPilot backend")

DATABASE_URL = "postgresql+psycopg://bizpilot:abc123@localhost:5432/bizpilot"
engine = create_engine(DATABASE_URL)

class PurchaseItem(BaseModel):
    name: str
    qty: float
    unit: str

class PurchaseRequestIn(BaseModel):
    requester_name: str
    source_channel: str = "openclaw"
    raw_text: str
    supplier_name: str
    purchase_date: str
    items: List[PurchaseItem]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/purchase-requests")
def create_purchase_request(payload: PurchaseRequestIn):
    with engine.begin() as conn:
        requester = conn.execute(
            text("select id from users where name = :name limit 1"),
            {"name": payload.requester_name}
        ).fetchone()
        if not requester:
            raise HTTPException(status_code=400, detail="requester not found")

        supplier = conn.execute(
            text("select id from suppliers where name = :name limit 1"),
            {"name": payload.supplier_name}
        ).fetchone()
        if not supplier:
            raise HTTPException(status_code=400, detail="supplier not found")

        now = datetime.now()
        # request_no = f"PR-{now.strftime('%Y%m%d%H%M%S')}"
        request_no = f"PR-{now.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:6]}"

        pr_id = conn.execute(
            text("""
                insert into purchase_requests
                (request_no, requester_id, supplier_id, purchase_date, status, source_channel, raw_text, confirmed_at)
                values
                (:request_no, :requester_id, :supplier_id, :purchase_date, 'confirmed', :source_channel, :raw_text, now())
                returning id
            """),
            {
                "request_no": request_no,
                "requester_id": requester.id,
                "supplier_id": supplier.id,
                "purchase_date": payload.purchase_date,
                "source_channel": payload.source_channel,
                "raw_text": payload.raw_text,
            }
        ).scalar_one()

        for item in payload.items:
            product = conn.execute(
                text("select id from products where name = :name limit 1"),
                {"name": item.name}
            ).fetchone()

            conn.execute(
                text("""
                    insert into purchase_request_items
                    (purchase_request_id, product_id, product_name_snapshot, qty, unit)
                    values
                    (:purchase_request_id, :product_id, :product_name_snapshot, :qty, :unit)
                """),
                {
                    "purchase_request_id": pr_id,
                    "product_id": product.id if product else None,
                    "product_name_snapshot": item.name,
                    "qty": item.qty,
                    "unit": item.unit,
                }
            )

        conn.execute(
            text("""
                insert into event_logs (entity_type, entity_id, event_type, operator, raw_payload)
                values ('purchase_request', :entity_id, 'created', :operator, cast(:raw_payload as jsonb))
            """),
            {
                "entity_id": pr_id,
                "operator": payload.requester_name,
                "raw_payload": payload.model_dump_json(),
            }
        )

    return {
        "success": True,
        "request_no": request_no,
        "status": "confirmed"
    }
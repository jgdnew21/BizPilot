import re
from datetime import date, timedelta, datetime

from app.config import settings
from app.domain.purchase.material_request import MaterialRequestDraft, PurchaseSnapshot
from app.services.markdown_service import MarkdownService
from app.services.master_data_service import MasterDataService
from app.services.snapshot_service import SnapshotService
from app.integrations.erpnext_client import ErpnextClient


class MaterialRequestWorkflow:
    def __init__(self, master_data_service: MasterDataService, snapshot_service: SnapshotService, erpnext_client: ErpnextClient):
        self.master_data_service = master_data_service
        self.snapshot_service = snapshot_service
        self.erpnext_client = erpnext_client

    @staticmethod
    def _strip_non_item_segments(text: str) -> str:
        cleaned = text
        patterns = [
            r"供应商是?[\u4e00-\u9fa5A-Za-z0-9（）()·\-]+",
            r"入[\u4e00-\u9fa5A-Za-z0-9（）()·\-]*仓",
            r"入库到[\u4e00-\u9fa5A-Za-z0-9（）()·\-]*仓?",
        ]
        for pattern in patterns:
            cleaned = re.sub(pattern, " ", cleaned)
        return cleaned

    def parse_purchase_items(self, text: str):
        normalized = self._strip_non_item_segments(text)
        normalized = normalized.replace('要买', ' ').replace('购买', ' ').replace('采购', ' ')

        item_pattern = re.compile(
            r"(?P<name>[\u4e00-\u9fa5A-Za-z0-9（）()·\-]+?)\s*(?P<qty>\d+(?:\.\d+)?)\s*(?P<uom>斤|盒|个|箱|包|袋|瓶|件|kg|KG|千克)"
        )

        items = []
        for match in item_pattern.finditer(normalized):
            name = match.group("name").strip('，,。;；:： ') 
            if not name:
                continue
            qty = float(match.group("qty"))
            uom = match.group("uom")
            matched = self.master_data_service.match_item(name)
            items.append({"item_input_name": name, "qty": qty, "uom": uom, "matched_item": matched.model_dump()})
        return items

    def _parse(self, text: str):
        schedule_map = {"今天": 0, "明天": 1, "后天": 2}
        schedule_input = next((k for k in schedule_map if k in text), "未明确，默认今天")
        delta = schedule_map.get(schedule_input, 0)
        schedule_date = (date.today() + timedelta(days=delta)).isoformat()

        supplier = re.search(r"供应商([\u4e00-\u9fa5A-Za-z0-9]+)", text)
        supplier_input = supplier.group(1) if supplier else None
        warehouse = re.search(r"入([\u4e00-\u9fa5A-Za-z0-9]+仓?)", text)
        warehouse_input = warehouse.group(1) if warehouse else settings.default_warehouse_alias
        warehouse_defaulted = warehouse is None

        items = self.parse_purchase_items(text)
        return schedule_input, schedule_date, supplier_input, warehouse_input, warehouse_defaulted, items

    def prepare(self, session_id: str, user_id: str, user_name: str, text: str):
        schedule_input, schedule_date, supplier_input, warehouse_input, defaulted, items = self._parse(text)
        supplier = self.master_data_service.match_supplier(supplier_input)
        warehouse = self.master_data_service.match_warehouse(warehouse_input)
        draft = MaterialRequestDraft(
            session_id=session_id, user_id=user_id, user_name=user_name, raw_text=text,
            schedule_date=schedule_date, schedule_date_input=schedule_input,
            supplier=supplier, warehouse=warehouse, items=items,
        )
        draft.structured_payload = {
            "doc_type": "material_request", "schedule_date": schedule_date,
            "supplier": supplier.model_dump(), "warehouse": warehouse.model_dump(), "items": items,
        }
        draft.markdown_text = MarkdownService.build_material_request_markdown(draft, warehouse_defaulted=defaulted)

        snap = PurchaseSnapshot(
            snapshot_id=self.snapshot_service.generate_snapshot_id(), doc_type="material_request",
            session_id=session_id, user_id=user_id, status="pending_confirmation", raw_text=text,
            markdown_text=draft.markdown_text, structured_payload=draft.structured_payload,
        )
        self.snapshot_service.save(snap)
        return {"snapshot_id": snap.snapshot_id, "doc_type": snap.doc_type, "status": snap.status, "markdown_text": snap.markdown_text}

    def confirm(self, session_id: str, user_id: str, snapshot_id: str, confirm_text: str):
        snap = self.snapshot_service.get(snapshot_id)
        if not snap:
            return {"snapshot_id": snapshot_id, "doc_type": "material_request", "status": "invalid", "erpnext_doc_no": None, "message": "snapshot不存在", "error_code": "SNAPSHOT_NOT_FOUND"}
        if snap.session_id != session_id or snap.user_id != user_id:
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "会话或用户不匹配", "error_code": "IDENTITY_MISMATCH"}
        if snap.status != "pending_confirmation":
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "snapshot状态不可确认", "error_code": "INVALID_STATUS"}
        if confirm_text.strip() != "确认":
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "confirm_text必须为确认", "error_code": "INVALID_CONFIRM_TEXT"}

        payload = snap.structured_payload
        if payload["supplier"]["status"] != "matched":
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "供应商未匹配", "error_code": "UNMATCHED_SUPPLIER"}
        if payload["warehouse"]["status"] != "matched":
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "仓库未匹配", "error_code": "UNMATCHED_WAREHOUSE"}
        if not payload.get("items"):
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "未识别到商品明细", "error_code": "EMPTY_ITEMS"}

        erp_items = []
        for row in payload["items"]:
            m = row["matched_item"]
            if m["status"] != "matched":
                return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "商品未匹配", "error_code": "UNMATCHED_ITEM"}
            if row["uom"] != m["purchase_uom"]:
                return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "单位与采购单位不一致", "error_code": "UOM_MISMATCH"}
            erp_items.append({"item_code": m["item_code"], "qty": row["qty"], "uom": row["uom"], "schedule_date": payload["schedule_date"], "warehouse": payload["warehouse"]["warehouse_standard_name"]})

        erp_payload = {"doctype": "Material Request", "material_request_type": "Purchase", "schedule_date": payload["schedule_date"], "items": erp_items}
        try:
            name = self.erpnext_client.create_material_request(erp_payload)
            snap.status = "submitted"
            snap.confirmed_at = datetime.utcnow().isoformat()
            snap.submitted_at = datetime.utcnow().isoformat()
            snap.erpnext_doc_no = name
            self.snapshot_service.update(snap)
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "submitted", "erpnext_doc_no": name, "message": f"已创建 ERPNext 采购需求计划 MR：{name}", "error_code": None}
        except Exception:
            snap.status = "submit_failed"
            snap.error_message = "ERPNext API 调用失败"
            self.snapshot_service.update(snap)
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "submit_failed", "erpnext_doc_no": None, "message": "ERPNext API 调用失败", "error_code": "ERPNEXT_API_ERROR"}

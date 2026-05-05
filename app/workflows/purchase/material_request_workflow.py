from datetime import date, timedelta, datetime

from app.config import settings
from app.domain.validation import BusinessValidator
from app.domain.purchase.material_request import MaterialRequestDraft, PurchaseSnapshot
from app.services.markdown_service import MarkdownService
from app.services.master_data_service import MasterDataService
from app.services.snapshot_service import SnapshotService
from app.services.text_normalizer import TextNormalizer
from app.services.extractors import MaterialRequestExtractorOrchestrator
from app.integrations.erpnext_client import ErpnextClient


class MaterialRequestWorkflow:
    def __init__(self, master_data_service: MasterDataService, snapshot_service: SnapshotService, erpnext_client: ErpnextClient):
        self.master_data_service = master_data_service
        self.snapshot_service = snapshot_service
        self.erpnext_client = erpnext_client
        self.text_normalizer = TextNormalizer()
        self.extractor = MaterialRequestExtractorOrchestrator()

    def _parse(self, text: str):
        normalized = self.text_normalizer.normalize(text)
        extraction = self.extractor.extract(normalized)

        schedule_map = {"今天": 0, "明天": 1, "后天": 2}
        schedule_input = extraction.schedule_date_input or "未明确，默认今天"
        delta = schedule_map.get(extraction.schedule_date_input or "", 0)
        schedule_date = (date.today() + timedelta(days=delta)).isoformat()

        warehouse_input = extraction.warehouse_input or settings.default_warehouse_alias
        warehouse_defaulted = extraction.warehouse_input is None

        items = []
        for row in extraction.items:
            matched = self.master_data_service.match_item(row.item_input_name)
            items.append({
                "item_input_name": row.item_input_name,
                "qty": row.qty,
                "uom": row.uom,
                "matched_item": matched.model_dump(),
            })
        return schedule_input, schedule_date, extraction.supplier_input, warehouse_input, warehouse_defaulted, items

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
        validation_result = BusinessValidator.validate_material_request_payload(draft.structured_payload)
        draft.structured_payload.update({
            "draft_status": validation_result.status,
            "can_confirm": validation_result.can_confirm,
            "missing_fields": validation_result.missing_fields,
            "blocking_reasons": validation_result.blocking_reasons,
        })
        draft.markdown_text = MarkdownService.build_material_request_markdown(draft, validation_result, warehouse_defaulted=defaulted)

        snap = PurchaseSnapshot(
            snapshot_id=self.snapshot_service.generate_snapshot_id(), doc_type="material_request",
            session_id=session_id, user_id=user_id, status=validation_result.status, raw_text=text,
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
        if snap.status not in {"ready_for_confirmation", "needs_clarification", "blocked"}:
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "snapshot状态不可确认", "error_code": "INVALID_STATUS"}
        if confirm_text.strip() != "确认":
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "confirm_text必须为确认", "error_code": "INVALID_CONFIRM_TEXT"}

        payload = snap.structured_payload
        validation_result = BusinessValidator.validate_material_request_payload(payload)
        snapshot_draft_status = payload.get("draft_status", validation_result.status)
        snapshot_can_confirm = payload.get("can_confirm", validation_result.can_confirm)
        if snapshot_draft_status == "blocked":
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划存在未匹配或校验失败项，不能提交。请先修正后重新生成确认单。", "error_code": "BLOCKED_DRAFT"}
        if snapshot_draft_status == "needs_clarification" or not snapshot_can_confirm:
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划信息不完整，不能提交。请先补充缺失信息。", "error_code": "INCOMPLETE_DRAFT"}

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

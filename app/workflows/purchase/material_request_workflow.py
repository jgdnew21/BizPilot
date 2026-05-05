from datetime import date, timedelta, datetime

from app.config import settings
from app.domain.validation import BusinessValidator
from app.domain.purchase.material_request import MaterialRequestDraft, PurchaseSnapshot
from app.services.markdown_service import MarkdownService
from app.services.master_data_service import MasterDataService
from app.services.snapshot_service import SnapshotService
from app.services.text_normalizer import TextNormalizer
from app.services.extractors import MaterialRequestExtractorOrchestrator
from app.services.material_request_payload_builder import build_material_request_erpnext_payload
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
        return schedule_input, schedule_date, extraction.supplier_input, warehouse_input, warehouse_defaulted, items, extraction

    def prepare(self, session_id: str, user_id: str, user_name: str, text: str, previous_snapshot_id: str | None = None):
        previous_snapshot = None
        revision = 1
        input_text = text
        if previous_snapshot_id:
            previous_snapshot = self.snapshot_service.get(previous_snapshot_id)
            if not previous_snapshot:
                raise ValueError("previous_snapshot_id不存在")
            if previous_snapshot.session_id != session_id or previous_snapshot.user_id != user_id:
                raise ValueError("previous snapshot与当前会话或用户不匹配")
            revision = previous_snapshot.revision + 1
            input_text = (
                f"previous_draft:\n{previous_snapshot.structured_payload}\n\n"
                f"previous_markdown:\n{previous_snapshot.markdown_text}\n\n"
                f"user_update:\n{text}"
            )

        schedule_input, schedule_date, supplier_input, warehouse_input, defaulted, items, extraction = self._parse(input_text)
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
            "extractor_name": extraction.extractor_name,
            "extractor_warnings": extraction.warnings,
            "confidence": extraction.confidence,
        }
        validation_result = BusinessValidator.validate_material_request_payload(draft.structured_payload)
        draft.structured_payload.update({
            "draft_status": validation_result.status,
            "can_confirm": validation_result.can_confirm,
            "missing_fields": validation_result.missing_fields,
            "blocking_reasons": validation_result.blocking_reasons,
        })
        draft.markdown_text = MarkdownService.build_material_request_markdown(draft, validation_result, warehouse_defaulted=defaulted)
        if previous_snapshot:
            draft.markdown_text += "\n\n这是基于上一版确认单重新整理的版本。"

        snap = PurchaseSnapshot(
            snapshot_id=self.snapshot_service.generate_snapshot_id(), doc_type="material_request",
            session_id=session_id, user_id=user_id, status=validation_result.status, raw_text=text,
            markdown_text=draft.markdown_text, structured_payload=draft.structured_payload,
            previous_snapshot_id=previous_snapshot_id, revision=revision,
        )
        if previous_snapshot and previous_snapshot.status in {"ready_for_confirmation", "pending_confirmation"}:
            previous_snapshot.status = "superseded"
            self.snapshot_service.update(previous_snapshot)
        self.snapshot_service.save(snap)
        return {"snapshot_id": snap.snapshot_id, "doc_type": snap.doc_type, "status": snap.status, "markdown_text": snap.markdown_text}

    def confirm(self, session_id: str, user_id: str, snapshot_id: str, confirm_text: str):
        snap = self.snapshot_service.get(snapshot_id)
        if not snap:
            return {"snapshot_id": snapshot_id, "doc_type": "material_request", "status": "invalid", "erpnext_doc_no": None, "message": "找不到待确认的采购需求计划。", "error_code": "SNAPSHOT_NOT_FOUND"}
        if snap.session_id != session_id or snap.user_id != user_id:
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前确认请求与原采购需求不匹配，不能提交。", "error_code": "IDENTITY_MISMATCH"}
        if confirm_text.strip() != "确认":
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "请回复“确认”提交，或回复修改内容重新生成确认单。", "error_code": "INVALID_CONFIRM_TEXT"}
        if snap.status == "superseded":
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "该确认单已有更新版本，请确认最新确认单。", "error_code": "SNAPSHOT_SUPERSEDED"}
        if snap.status == "submitted":
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": snap.erpnext_doc_no, "message": "该采购需求计划已提交，请勿重复提交。", "error_code": "SNAPSHOT_ALREADY_SUBMITTED"}

        payload = snap.structured_payload
        if not payload:
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划信息不完整，不能提交。", "error_code": "INCOMPLETE_DRAFT"}

        snapshot_draft_status = payload.get("draft_status")
        snapshot_can_confirm = payload.get("can_confirm")
        if snapshot_draft_status != "ready_for_confirmation":
            if snapshot_draft_status == "needs_clarification":
                return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划信息不完整，不能提交。", "error_code": "INCOMPLETE_DRAFT"}
            if snapshot_draft_status in {"blocked", "submit_failed"}:
                return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划存在未匹配或校验失败项，不能提交。", "error_code": "BLOCKED_DRAFT"}
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划状态不可确认，不能提交。", "error_code": "INVALID_STATUS"}
        if snapshot_can_confirm is not True:
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划信息不完整，不能提交。", "error_code": "INCOMPLETE_DRAFT"}

        items = payload.get("items") or []
        supplier = payload.get("supplier") or {}
        warehouse = payload.get("warehouse") or {}
        if not items:
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划信息不完整，不能提交。", "error_code": "INCOMPLETE_DRAFT"}
        if supplier.get("status") != "matched":
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划存在未匹配或校验失败项，不能提交。", "error_code": "BLOCKED_DRAFT"}
        if warehouse.get("status") != "matched":
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划存在未匹配或校验失败项，不能提交。", "error_code": "BLOCKED_DRAFT"}

        for row in items:
            m = row.get("matched_item") or {}
            if m.get("status") != "matched":
                return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划存在未匹配或校验失败项，不能提交。", "error_code": "BLOCKED_DRAFT"}
            if not (row.get("warehouse") or warehouse.get("warehouse_standard_name")):
                return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划信息不完整，不能提交。", "error_code": "INCOMPLETE_DRAFT"}
            if (row.get("qty") or 0) <= 0:
                return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划存在未匹配或校验失败项，不能提交。", "error_code": "BLOCKED_DRAFT"}
            if row.get("uom") != m.get("purchase_uom"):
                return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "invalid", "erpnext_doc_no": None, "message": "当前采购需求计划存在未匹配或校验失败项，不能提交。", "error_code": "BLOCKED_DRAFT"}

        erp_payload = build_material_request_erpnext_payload(snap)
        try:
            name = self.erpnext_client.create_material_request(erp_payload)
            snap.status = "submitted"
            snap.confirmed_at = datetime.utcnow().isoformat()
            snap.submitted_at = datetime.utcnow().isoformat()
            snap.erpnext_doc_no = name
            self.snapshot_service.update(snap)
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "submitted", "erpnext_doc_no": name, "message": f"已创建 ERPNext 采购需求计划 MR：{name}", "error_code": None}
        except Exception as exc:
            snap.status = "submit_failed"
            snap.error_message = f"提交 ERPNext 失败：{str(exc)}"
            self.snapshot_service.update(snap)
            return {"snapshot_id": snapshot_id, "doc_type": snap.doc_type, "status": "submit_failed", "erpnext_doc_no": None, "message": snap.error_message, "error_code": "ERPNEXT_API_ERROR"}

"""Purchase inbound (post-purchase) workflow.

This workflow handles the reporting-after-purchase path:
- prepare: parse/match/validate/render markdown/save snapshot
- confirm: read snapshot and create ERPNext Purchase Receipt draft

Safety boundaries:
- prepare does NOT write ERPNext.
- confirm MUST use snapshot and must not re-parse raw user text.
- create draft only; do not submit automatically.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

from app.config import settings
from app.domain.purchase.material_request import PurchaseSnapshot
from app.integrations.erpnext_client import ErpnextApiError, ErpnextClient
from app.repositories.master_data_cache_repository import MasterDataCacheRepository
from app.schemas.master_data_match import MatchResult, ValidationResult
from app.schemas.purchase.purchase_inbound import (
    PurchaseInboundConfirmRequest,
    PurchaseInboundPrepareRequest,
    ValidationIssue,
)
from app.services.master_data_match_service import MasterDataMatchService
from app.services.snapshot_service import SnapshotService


class PurchaseInboundWorkflow:
    """Prepare purchase-inbound confirmations from plain-text reports.

    This workflow intentionally stops at prepare: it parses and validates a text
    report, renders a Markdown confirmation sheet, and persists an internal
    snapshot for a later confirm step. It never creates ERPNext Purchase Receipt
    documents.
    """

    _LINE_PATTERN = re.compile(
        r"(?P<name>[^\d，,。；;\n]+?)\s*"
        r"(?P<qty>\d+(?:\.\d+)?)\s*"
        r"(?P<uom>[\u4e00-\u9fffA-Za-z]+)\s*"
        r"(?P<rate>\d+(?:\.\d+)?)\s*"
        r"(?:元?\s*/\s*[\u4e00-\u9fffA-Za-z]+|元)?\s*"
        r"(?P<amount>\d+(?:\.\d+)?)?"
    )
    _TOTAL_PATTERN = re.compile(r"(?:共|合计|总计)\s*(?P<total>\d+(?:\.\d+)?)\s*元?")

    def __init__(
        self,
        match_service: MasterDataMatchService,
        snapshot_service: SnapshotService,
        erpnext_client: ErpnextClient | None = None,
    ):
        self.match_service = match_service
        self.snapshot_service = snapshot_service
        # Keep constructor test-friendly: unit tests can build workflow without a real ERP client
        # when they only validate prepare behavior.
        self.erpnext_client = erpnext_client or ErpnextClient(
            settings.erpnext_base_url,
            settings.erpnext_api_key,
            settings.erpnext_api_secret,
        )

    @classmethod
    def from_settings(cls) -> "PurchaseInboundWorkflow":
        return cls(
            match_service=MasterDataMatchService(
                MasterDataCacheRepository(settings.master_data_cache_db)
            ),
            snapshot_service=SnapshotService.from_settings(),
            erpnext_client=ErpnextClient(
                settings.erpnext_base_url,
                settings.erpnext_api_key,
                settings.erpnext_api_secret,
            ),
        )

    def confirm(self, req: PurchaseInboundConfirmRequest) -> dict[str, Any]:
        """Confirm inbound strictly from snapshot and create ERPNext Purchase Receipt draft.

        Idempotency: if draft was already created for the snapshot, return existing ERP doc name
        instead of creating a duplicate document.
        """
        if req.confirm_text.strip() != "确认入库":
            return {
                "status": "invalid_confirm_text",
                "snapshot_id": req.snapshot_id or "",
                "message": "请回复“确认入库”以创建采购入库草稿。",
                "error_detail": None,
            }

        snap = self._resolve_snapshot(req)
        if not snap:
            return {
                "status": "snapshot_not_found",
                "snapshot_id": req.snapshot_id or "",
                "message": "未找到可确认的采购入库快照。",
                "error_detail": None,
            }
        if snap.session_id != req.session_id or snap.user_id != req.user_id:
            return {
                "status": "snapshot_identity_mismatch",
                "snapshot_id": snap.snapshot_id,
                "message": "snapshot 与当前会话或用户不匹配。",
                "error_detail": None,
            }
        if snap.status == "erp_draft_created" and snap.erp_purchase_receipt_name:
            return {
                "status": "erp_draft_created",
                "snapshot_id": snap.snapshot_id,
                "erp_purchase_receipt_name": snap.erp_purchase_receipt_name,
                "message": f"已创建 ERPNext 采购入库草稿：{snap.erp_purchase_receipt_name}，请在 ERPNext 中复核后提交。",
                "error_detail": None,
            }
        if snap.status != "pending_confirmation":
            return {
                "status": "invalid_snapshot_status",
                "snapshot_id": snap.snapshot_id,
                "message": f"当前 snapshot 状态为 {snap.status}，不可确认入库。",
                "error_detail": None,
            }

        payload = self._build_purchase_receipt_payload(snap)
        try:
            pr_name = self.erpnext_client.create_purchase_receipt(payload)
            snap.status = "erp_draft_created"
            snap.erp_purchase_receipt_name = pr_name
            snap.submitted_at = datetime.utcnow().isoformat()
            snap.error_message = None
            self.snapshot_service.update(snap)
            return {
                "status": "erp_draft_created",
                "snapshot_id": snap.snapshot_id,
                "erp_purchase_receipt_name": pr_name,
                "message": f"已创建 ERPNext 采购入库草稿：{pr_name}，请在 ERPNext 中复核后提交。",
                "error_detail": None,
            }
        except ErpnextApiError as exc:
            snap.status = "erp_create_failed"
            snap.error_message = exc.response_text_summary
            self.snapshot_service.update(snap)
            return {
                "status": "erp_create_failed",
                "snapshot_id": snap.snapshot_id,
                "erp_purchase_receipt_name": None,
                "message": f"创建 ERPNext 采购入库草稿失败：{exc.response_text_summary}",
                "error_detail": exc.response_text_summary,
            }

    def _resolve_snapshot(
        self, req: PurchaseInboundConfirmRequest
    ) -> PurchaseSnapshot | None:
        if req.snapshot_id:
            return self.snapshot_service.get(req.snapshot_id)
        return self.snapshot_service.latest_by_session_and_status(
            req.session_id, "pending_confirmation", doc_type="purchase_inbound"
        )

    def _build_purchase_receipt_payload(self, snap: PurchaseSnapshot) -> dict[str, Any]:
        """Build ERP payload from stored snapshot only (no re-parsing, no re-matching)."""
        structured = snap.structured_payload or {}
        supplier = (structured.get("supplier") or {}).get("erp_supplier_name")
        warehouse = structured.get("warehouse")
        items = structured.get("items") or []
        if not supplier or not warehouse or not items:
            raise ErpnextApiError(400, "snapshot", "structured_payload 不完整")
        erp_items = []
        for row in items:
            item_code = row.get("item_code")
            qty = float(row.get("qty") or 0)
            rate = float(row.get("rate") or 0)
            if not item_code:
                raise ErpnextApiError(400, "snapshot", "存在未匹配 item_code")
            if qty <= 0:
                raise ErpnextApiError(400, "snapshot", "存在数量小于等于 0 的明细")
            if rate < 0:
                raise ErpnextApiError(400, "snapshot", "存在单价小于 0 的明细")
            erp_items.append(
                {
                    "item_code": item_code,
                    "qty": qty,
                    "uom": row.get("uom"),
                    "rate": rate,
                    "amount": float(row.get("amount") or qty * rate),
                    "warehouse": warehouse,
                }
            )
        return {
            "doctype": "Purchase Receipt",
            "supplier": supplier,
            "posting_date": datetime.utcnow().date().isoformat(),
            "set_warehouse": warehouse,
            "items": erp_items,
            "remarks": f"来源：{snap.source_channel or 'unknown'} 采购报单；snapshot_id={snap.snapshot_id}；原始报单：{snap.raw_text}",
        }

    def prepare(self, req: PurchaseInboundPrepareRequest) -> dict[str, Any]:
        """Prepare inbound confirmation markdown and snapshot without writing ERPNext."""
        input_text = req.get_input_text()
        if not input_text:
            return {
                "status": "needs_user_fix",
                "snapshot_id": "",
                "markdown": "未收到采购报单文本，请重新发送采购内容。",
                "validation": {
                    "status": "failed",
                    "warnings": [],
                    "errors": [
                        ValidationIssue(
                            type="empty_input_text",
                            message="未收到采购报单文本，请重新发送采购内容。",
                        ).model_dump()
                    ],
                },
            }

        normalized_text = self._normalize_prepare_text(input_text)
        parsed_lines = self._parse_lines(normalized_text)
        reported_total = self._parse_reported_total(normalized_text)
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []

        supplier_match = self.match_service.match_supplier(
            req.supplier_name, default_supplier=settings.default_purchase_supplier
        )
        if supplier_match.status != "matched" and req.supplier_name:
            default_supplier_match = self.match_service.match_supplier(
                None, default_supplier=settings.default_purchase_supplier
            )
            if default_supplier_match.status == "matched":
                warnings.append(
                    ValidationIssue(
                        type="supplier_fallback_default",
                        message=f"供应商“{req.supplier_name}”不存在，已使用默认供应商",
                    )
                )
                supplier_match = default_supplier_match

        warehouse_validation = self.match_service.validate_warehouse(
            req.warehouse or settings.default_purchase_warehouse
        )
        if supplier_match.status != "matched":
            errors.append(
                ValidationIssue(
                    type=f"supplier_{supplier_match.status}",
                    message=supplier_match.message,
                )
            )
        if warehouse_validation.status != "matched":
            errors.append(
                ValidationIssue(
                    type="warehouse_invalid",
                    message=warehouse_validation.message,
                )
            )
        if not parsed_lines:
            errors.append(
                ValidationIssue(type="no_items", message="未解析到采购入库明细")
            )

        items = []
        calculated_total = Decimal("0")
        for line_no, row in enumerate(parsed_lines, start=1):
            item_match = self.match_service.match_item(row["item_input_name"])
            uom_validation = self.match_service.validate_uom(row["uom"])
            line_errors: list[str] = []
            line_warnings: list[str] = []
            qty = Decimal(str(row["qty"]))
            rate = Decimal(str(row["rate"]))
            amount = (
                Decimal(str(row["amount"]))
                if row.get("amount") is not None
                else self._money(qty * rate)
            )
            expected_amount = self._money(qty * rate)
            calculated_total += expected_amount

            if qty <= 0:
                line_errors.append("数量必须大于 0")
                errors.append(
                    ValidationIssue(
                        type="qty_invalid", message="数量必须大于 0", line_no=line_no
                    )
                )
            if rate < 0:
                line_errors.append("单价不能小于 0")
                errors.append(
                    ValidationIssue(
                        type="rate_invalid", message="单价不能小于 0", line_no=line_no
                    )
                )
            if abs(amount - expected_amount) > Decimal("0.01"):
                message = f"明细金额 {self._format_money(amount)} 与数量×单价 {self._format_money(expected_amount)} 不一致"
                line_errors.append(message)
                errors.append(
                    ValidationIssue(
                        type="line_amount_mismatch", message=message, line_no=line_no
                    )
                )
            if item_match.status != "matched":
                message = self._item_error_message(row["item_input_name"], item_match)
                line_errors.append(message)
                errors.append(
                    ValidationIssue(
                        type=f"item_{item_match.status}",
                        message=message,
                        line_no=line_no,
                    )
                )
            if uom_validation.status != "matched":
                line_errors.append(uom_validation.message)
                errors.append(
                    ValidationIssue(
                        type="uom_invalid",
                        message=uom_validation.message,
                        line_no=line_no,
                    )
                )

            validation_status = "passed" if not line_errors else "failed"
            items.append(
                {
                    "line_no": line_no,
                    "item_input_name": row["item_input_name"],
                    "item_code": self._selected_value(item_match, "item_code"),
                    "item_name_snapshot": self._selected_value(item_match, "item_name"),
                    "qty": float(qty),
                    "uom": row["uom"],
                    "rate": float(rate),
                    "amount": float(self._money(amount)),
                    "match_status": item_match.status,
                    "validation_status": validation_status,
                    "match_candidates": item_match.candidates,
                    "validation_messages": line_errors or line_warnings,
                }
            )

        calculated_total = self._money(calculated_total)
        if reported_total is not None and abs(
            Decimal(str(reported_total)) - calculated_total
        ) > Decimal("0.01"):
            warnings.append(
                ValidationIssue(
                    type="reported_total_mismatch",
                    message=f"报单合计 {self._format_money(Decimal(str(reported_total)))} 与系统计算合计 {self._format_money(calculated_total)} 不一致",
                )
            )

        status = "needs_user_fix" if errors else "pending_confirmation"
        validation = {
            "status": "failed" if errors else "passed",
            "warnings": [warning.model_dump() for warning in warnings],
            "errors": [error.model_dump() for error in errors],
        }
        structured_payload = {
            "supplier": self._supplier_payload(req.supplier_name, supplier_match),
            "warehouse": self._warehouse_payload(req.warehouse, warehouse_validation),
            "items": items,
            "reported_total": (
                float(Decimal(str(reported_total)))
                if reported_total is not None
                else None
            ),
            "calculated_total": float(calculated_total),
        }
        markdown = self._render_markdown(
            status=status,
            req=req,
            structured_payload=structured_payload,
            validation=validation,
        )
        snapshot_id = self._generate_snapshot_id()
        snapshot = PurchaseSnapshot(
            snapshot_id=snapshot_id,
            doc_type="purchase_inbound",
            session_id=req.session_id,
            user_id=req.user_id,
            user_name=req.user_name,
            source_channel=req.source_channel,
            source_type=req.source_type,
            status=status,
            raw_text=input_text,
            raw_supplier_name=req.supplier_name,
            erp_supplier_name=structured_payload["supplier"].get("erp_supplier_name"),
            warehouse=structured_payload["warehouse"],
            markdown_text=markdown,
            structured_payload=structured_payload,
            validation_result=validation,
        )
        self.snapshot_service.save(snapshot)
        return {
            "status": status,
            "snapshot_id": snapshot_id,
            "markdown": markdown,
            "validation": validation,
        }

    def _parse_lines(self, text: str) -> list[dict[str, Any]]:
        rows = []
        without_total = self._TOTAL_PATTERN.sub("", text)
        for match in self._LINE_PATTERN.finditer(without_total):
            name = self._clean_item_name(match.group("name"))
            if not name:
                continue
            rows.append(
                {
                    "item_input_name": name,
                    "qty": float(match.group("qty")),
                    "uom": match.group("uom"),
                    "rate": float(match.group("rate")),
                    "amount": (
                        float(match.group("amount")) if match.group("amount") else None
                    ),
                }
            )
        return rows

    def _normalize_prepare_text(self, text: str) -> str:
        normalized = re.sub(r"[，,]\s*供应商\s*[^\n，,。；;]+", "", text)
        normalized = normalized.replace("单价", "")
        normalized = normalized.replace("，", " ").replace(",", " ")
        return normalized

    def _parse_reported_total(self, text: str) -> float | None:
        match = self._TOTAL_PATTERN.search(text)
        return float(match.group("total")) if match else None

    def _clean_item_name(self, name: str) -> str:
        cleaned = name.strip(" ，,。；;：:\t\r\n")
        if "：" in cleaned:
            cleaned = cleaned.rsplit("：", 1)[-1]
        if ":" in cleaned:
            cleaned = cleaned.rsplit(":", 1)[-1]
        for prefix in (
            "我今天买了",
            "我买了",
            "今天采购",
            "采购",
            "今天",
            "报单",
            "入库",
            "采购报单",
            "买了",
        ):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :]
        return cleaned.strip(" ，,。；;：:")

    def _supplier_payload(
        self, raw_supplier_name: str | None, supplier_match: MatchResult
    ) -> dict[str, Any]:
        selected = supplier_match.selected or {}
        return {
            "raw_supplier_name": raw_supplier_name,
            "erp_supplier_name": selected.get("erp_supplier_name")
            or selected.get("supplier_name"),
            "match_status": supplier_match.status,
        }

    def _warehouse_payload(
        self, raw_warehouse: str | None, warehouse_validation: ValidationResult
    ) -> str | None:
        selected = warehouse_validation.selected or {}
        return (
            selected.get("warehouse")
            or selected.get("warehouse_name")
            or raw_warehouse
            or settings.default_purchase_warehouse
        )

    def _render_markdown(
        self,
        status: str,
        req: PurchaseInboundPrepareRequest,
        structured_payload: dict[str, Any],
        validation: dict[str, Any],
    ) -> str:
        title_status = "待确认" if status == "pending_confirmation" else "需修正"
        status_text = "待确认" if status == "pending_confirmation" else "需修正"
        source = (
            "微信文字报单"
            if req.source_channel == "wechat" and req.source_type == "text"
            else f"{req.source_channel}/{req.source_type}"
        )
        lines = [
            f"# 采购入库确认单（{title_status}）",
            "",
            f"来源：{source}  ",
            f"供应商：{structured_payload['supplier'].get('erp_supplier_name') or req.supplier_name or settings.default_purchase_supplier or '未匹配'}  ",
            f"入库仓库：{structured_payload['warehouse'] or '未匹配'}  ",
            f"状态：{status_text}  ",
            "",
            "| # | 报单商品 | ERP商品 | 数量 | 单位 | 单价 | 金额 | 状态 |",
            "|---|---|---|---:|---|---:|---:|---|",
        ]
        for item in structured_payload["items"]:
            erp_item = (
                item.get("item_name_snapshot")
                or self._candidate_text(item.get("match_candidates", []))
                or "未匹配"
            )
            line_status = (
                "已匹配"
                if item["validation_status"] == "passed"
                else self._line_status_text(item)
            )
            lines.append(
                "| {line_no} | {item_input_name} | {erp_item} | {qty:g} | {uom} | {rate:.2f} | {amount:.2f} | {line_status} |".format(
                    erp_item=erp_item,
                    line_status=line_status,
                    **item,
                )
            )
        lines.extend(
            [
                "",
                f"报单合计：{self._format_optional_money(structured_payload.get('reported_total'))}  ",
                f"系统计算合计：{structured_payload['calculated_total']:.2f}  ",
            ]
        )
        if validation["warnings"]:
            lines.extend(["", "## 提醒"])
            lines.extend(
                f"- {warning['message']}" for warning in validation["warnings"]
            )
        if status == "pending_confirmation":
            lines.extend(["", "回复“确认入库”后，将创建 ERPNext 采购入库草稿。"])
        else:
            lines.extend(["", "## 需要修正"])
            lines.extend(f"- {error['message']}" for error in validation["errors"])
            lines.append("")
            lines.append("请补充商品名称、单位、仓库或金额信息后重新提交。")
        return "\n".join(lines)

    def _line_status_text(self, item: dict[str, Any]) -> str:
        if item["match_status"] == "ambiguous":
            return "商品不明确"
        if item["match_status"] == "not_found":
            return "商品未匹配"
        if item["match_status"] == "disabled":
            return "商品已禁用"
        if item.get("validation_messages"):
            return item["validation_messages"][0]
        return "需修正"

    def _candidate_text(self, candidates: list[dict[str, Any]]) -> str:
        names = [
            candidate.get("item_name") or candidate.get("item_code")
            for candidate in candidates[:3]
        ]
        names = [name for name in names if name]
        return "候选：" + " / ".join(names) if names else ""

    def _item_error_message(self, item_name: str, item_match: MatchResult) -> str:
        if item_match.status == "ambiguous":
            return f"商品“{item_name}”匹配到多个 ERP 商品，请明确选择"
        if item_match.status == "disabled":
            return f"商品“{item_name}”已在 ERP 中禁用"
        return f"商品“{item_name}”未匹配到 ERP 商品"

    def _selected_value(self, result: MatchResult, key: str) -> Any:
        return (result.selected or {}).get(key)

    def _money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _format_money(self, value: Decimal) -> str:
        return f"{self._money(value):.2f}"

    def _format_optional_money(self, value: float | None) -> str:
        return "未提供" if value is None else f"{value:.2f}"

    def _generate_snapshot_id(self) -> str:
        return f"pin_{datetime.utcnow().strftime('%Y%m%d')}_{uuid4().hex[:6]}"

from app.domain.purchase.material_request import MaterialRequestDraft
from app.domain.validation import ValidationResult


class MarkdownService:
    @staticmethod
    def build_material_request_markdown(draft: MaterialRequestDraft, validation_result: ValidationResult, warehouse_defaulted: bool = False) -> str:
        lines = [
            "## 采购需求计划（待确认）",
            "",
            "| # | 商品 | 数量 | 单位 | ERP匹配商品 | 状态 |",
            "|---|---|---:|---|---|---|",
        ]
        for idx, row in enumerate(draft.items, start=1):
            status = "已匹配" if row["matched_item"]["status"] == "matched" else "未匹配"
            erp_name = row["matched_item"].get("item_name") or "-"
            lines.append(f"| {idx} | {row['item_input_name']} | {row['qty']} | {row['uom']} | {erp_name} | {status} |")

        wh_label = f"{draft.warehouse.warehouse_input} → {draft.warehouse.warehouse_standard_name}"
        if warehouse_defaulted:
            wh_label += "（默认）"
        lines += [
            "",
            f"- **供应商**：{draft.supplier.supplier_input} → {draft.supplier.supplier_standard_name}",
            f"- **需求日期**：{draft.schedule_date_input} → {draft.schedule_date}",
            f"- **预计入库仓库**：{wh_label}",
            f"- **录入人**：{draft.user_name}",
            "",
        ]
        if "items" in validation_result.missing_fields:
            lines.append("⚠️ 未识别到商品明细，暂不能提交。")
            lines.append("请按“商品 + 数量 + 单位”的格式补充，例如：五常大米 80 斤。")
            lines.append("")
            return "\n".join(lines)

        if validation_result.status != "ready_for_confirmation":
            lines.append("⚠️ 存在未匹配项，暂不能提交。")
            lines.append("请根据上方提示修正商品、供应商、仓库或单位后，重新生成确认单。")
            lines.append("")
            return "\n".join(lines)

        lines.append("请回复 **“确认”** 提交采购需求计划；如需修改，请直接回复修改内容。")
        return "\n".join(lines)

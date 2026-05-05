from app.domain.purchase.material_request import MaterialRequestDraft
from app.domain.validation import ValidationResult


class MarkdownService:
    @staticmethod
    def build_material_request_markdown(draft: MaterialRequestDraft, validation_result: ValidationResult, warehouse_defaulted: bool = False) -> str:
        title_map = {
            "ready_for_confirmation": "## 采购需求计划（待确认）",
            "needs_clarification": "## 采购需求计划（需补充）",
            "blocked": "## 采购需求计划（暂不能提交）",
        }
        lines = [
            title_map[validation_result.status],
            "",
        ]
        if draft.items:
            lines += [
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
        if validation_result.status == "needs_clarification":
            lines.append("我识别到你想创建采购需求计划，但还缺少必要信息：")
            lines.append("")
            lines.append("- **商品明细**：未识别到完整的“商品 + 数量 + 单位”")
            lines.append("")
            lines.append("请补充商品、数量和单位，例如：")
            lines.append("")
            lines.append("五常大米 80 斤")
            lines.append("")
            return "\n".join(lines)

        if validation_result.status == "blocked":
            lines.append("⚠️ 存在未匹配项，暂不能提交。")
            lines.append("请根据上方提示修正商品、供应商、仓库或单位后，重新生成确认单。")
            lines.append("")
            return "\n".join(lines)

        lines.append("请回复 **“确认”** 提交采购需求计划；如需修改，请直接回复修改内容。")
        return "\n".join(lines)

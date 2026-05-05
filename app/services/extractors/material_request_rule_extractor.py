from __future__ import annotations

import re

from app.domain.extraction import ExtractionResult, NormalizedText
from app.domain.purchase.material_request import PurchaseLineInput


class RuleBasedMaterialRequestExtractor:
    @staticmethod
    def _strip_non_item_segments(text: str) -> str:
        cleaned = text
        patterns = [
            r"(?:供应商|供货商|供应单位|供货单位)\s*(?:是|为|叫|:|：|=)?\s*[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+",
            r"(?:从|找)\s*[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+\s*采购",
            r"(?:预计)?\s*入库仓库\s*[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+",
            r"入库到\s*[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+仓?",
            r"入库\s*[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+仓?",
            r"入\s*[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+仓?",
            r"仓库\s*(?:是|为|:|：|=)?\s*[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+",
            r"放\s*[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+仓?",
        ]
        for pattern in patterns:
            cleaned = re.sub(pattern, " ", cleaned)
        return cleaned

    @staticmethod
    def _parse_supplier_input(text: str) -> str | None:
        keyword_pattern = re.compile(
            r"(?:供应商|供货商|供应单位|供货单位)\s*(?:是|为|叫|:|：|=)?\s*(?P<supplier>[^，,。；;\n]+)"
        )
        from_or_zhao_pattern = re.compile(r"(?:从|找)(?P<supplier>[\u4e00-\u9fa5A-Za-z0-9（）()·\-]+)采购")

        for pattern in (keyword_pattern, from_or_zhao_pattern):
            match = pattern.search(text)
            if not match:
                continue

            supplier = (match.group("supplier") or "").strip()
            supplier = re.sub(r"^(?:是|为|叫|:|：|=|\s)+", "", supplier).strip()
            supplier = re.split(r"(?:，|,|。|；|;|\n|入库|入|仓库|预计入库仓库)", supplier, maxsplit=1)[0].strip()
            if supplier in {"", "是", "为", "叫"}:
                return None
            return supplier
        return None

    @staticmethod
    def _parse_warehouse_input(text: str) -> str | None:
        patterns = [
            re.compile(r"(?:预计)?\s*入库仓库\s*(?P<warehouse>[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+)"),
            re.compile(r"入库到\s*(?P<warehouse>[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+仓?)"),
            re.compile(r"入库\s*(?P<warehouse>[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+仓?)"),
            re.compile(r"入\s*(?P<warehouse>[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+仓?)"),
            re.compile(r"仓库\s*(?:是|为|:|：|=)?\s*(?P<warehouse>[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+仓?)"),
            re.compile(r"放\s*(?P<warehouse>[\u4e00-\u9fa5A-Za-z0-9（）()·\-.]+仓?)"),
        ]
        for pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            warehouse = (match.group("warehouse") or "").strip()
            warehouse = re.sub(r"^(?:是|为|叫|:|：|=|\s)+", "", warehouse).strip()
            warehouse = re.split(r"(?:，|,|。|；|;|\n)", warehouse, maxsplit=1)[0].strip()
            if warehouse:
                return warehouse
        return None

    def extract(self, normalized: NormalizedText) -> ExtractionResult:
        text = normalized.normalized_text
        schedule_input = next((k for k in ("今天", "明天", "后天") if k in text), None)
        supplier_input = self._parse_supplier_input(text)

        warehouse_input = self._parse_warehouse_input(text)

        item_text = self._strip_non_item_segments(text)
        item_text = item_text.replace("要买", " ").replace("购买", " ").replace("采购", " ")

        item_pattern = re.compile(
            r"(?P<name>[\u4e00-\u9fa5A-Za-z0-9（）()·\-]+?)\s*(?P<qty>\d+(?:\.\d+)?)\s*(?P<uom>斤|盒|个|箱|包|袋|瓶|件|kg|KG|千克)"
        )
        items: list[PurchaseLineInput] = []
        for match in item_pattern.finditer(item_text):
            name = match.group("name").strip("，,。;；:： ")
            if not name:
                continue
            items.append(PurchaseLineInput(item_input_name=name, qty=float(match.group("qty")), uom=match.group("uom")))

        return ExtractionResult(
            raw_text=normalized.raw_text,
            normalized_text=normalized.normalized_text,
            schedule_date_input=schedule_input,
            supplier_input=supplier_input,
            warehouse_input=warehouse_input,
            items=items,
        )

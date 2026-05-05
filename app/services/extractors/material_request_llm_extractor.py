from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.domain.extraction import ExtractionResult, NormalizedText
from app.domain.purchase.material_request import PurchaseLineInput
from app.services.extractors.base import BaseMaterialRequestExtractor
from app.services.llm_client import LlmClient, LlmClientError


SYSTEM_PROMPT = """你是 BizPilot 的采购需求计划 MR 字段抽取器。
你只负责从用户自然语言中抽取采购需求计划字段。
你必须只返回 JSON，不要返回 Markdown，不要解释。

必须遵守：
1. 不要编造用户没说的信息。
2. 没有明确数量时，qty = null。
3. 没有明确单位时，uom = null。
4. 没有明确供应商时，supplier_input = null。
5. 没有明确仓库时，warehouse_input = null。
6. 不要输出 ERPNext item_code。
7. 不要输出 ERPNext supplier 标准名称。
8. 不要输出 ERPNext warehouse 标准名称。
9. 不要判断是否可以提交。
10. 不要生成用户确认单。
11. 只抽取候选字段。
12. 如果用户是在说实际买回来了、已经下单、已经入库，则 intent 不应是 create_material_request。"""


class LlmExtractedItem(BaseModel):
    item_input_name: str | None = None
    qty: float | None = None
    uom: str | None = None
    evidence: str | None = None

    @field_validator("qty")
    @classmethod
    def validate_qty(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("qty must be greater than 0")
        return value


class LlmMaterialRequestExtraction(BaseModel):
    intent: str
    confidence: float
    schedule_date_input: str | None = None
    supplier_input: str | None = None
    warehouse_input: str | None = None
    items: list[LlmExtractedItem] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("confidence must be in [0,1]")
        return value


class LlmMaterialRequestExtractor(BaseMaterialRequestExtractor):
    name = "llm"

    def __init__(self, llm_client: LlmClient | None = None):
        self.llm_client = llm_client or LlmClient()

    def extract(self, normalized_text: NormalizedText) -> ExtractionResult:
        user_prompt = (
            f"raw_text: {normalized_text.raw_text}\n"
            f"normalized_text: {normalized_text.normalized_text}\n"
            "按指定 JSON schema 输出。"
        )
        warnings: list[str] = []
        try:
            raw = self.llm_client.chat_json(SYSTEM_PROMPT, user_prompt)
            parsed = LlmMaterialRequestExtraction.model_validate(raw)
        except (LlmClientError, ValidationError, Exception) as exc:
            return ExtractionResult(
                raw_text=normalized_text.raw_text,
                normalized_text=normalized_text.normalized_text,
                extractor_name=self.name,
                warnings=[f"LLM extraction failed: {str(exc)}"],
            )

        items: list[PurchaseLineInput] = []
        for item in parsed.items:
            if not item.item_input_name:
                warnings.append("Dropped one item because item_input_name is empty.")
                continue
            if item.qty is None or item.uom is None:
                parsed.missing_fields.extend([f"qty:{item.item_input_name}" if item.qty is None else "", f"uom:{item.item_input_name}" if item.uom is None else ""])
                continue
            items.append(PurchaseLineInput(item_input_name=item.item_input_name, qty=item.qty, uom=item.uom))

        warnings.extend(parsed.warnings)
        warnings.extend([f"missing_field:{x}" for x in parsed.missing_fields if x])

        return ExtractionResult(
            raw_text=normalized_text.raw_text,
            normalized_text=normalized_text.normalized_text,
            intent=parsed.intent,
            confidence=parsed.confidence,
            schedule_date_input=parsed.schedule_date_input,
            supplier_input=parsed.supplier_input,
            warehouse_input=parsed.warehouse_input,
            items=items,
            extractor_name=self.name,
            warnings=warnings,
        )

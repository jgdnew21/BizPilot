"""Master data matching service over local cache.

Priority strategy: exact -> normalized exact -> fuzzy/contains -> ambiguous/not_found.
When no unique item can be determined, the service must not auto-select an item.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import logging
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)
from app.config import settings
from app.repositories.master_data_cache_repository import MasterDataCacheRepository
from app.schemas.master_data_match import MatchResult, ValidationResult


class MasterDataMatchService:
    """Rule-based search, match, and validation service for cached ERPNext master data."""

    def __init__(self, repository: MasterDataCacheRepository):
        self.repository = repository

    def search_items(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return [
            self._item_result(row, score, match_type)
            for row, score, match_type in self._search(
                query, self.repository.list_items(), ("item_code", "item_name"), limit
            )
        ]

    def search_suppliers(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return [
            self._supplier_result(row, score, match_type)
            for row, score, match_type in self._search(
                query,
                self.repository.list_suppliers(),
                ("supplier", "supplier_name"),
                limit,
            )
        ]

    def search_warehouses(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return [
            self._warehouse_result(row, score, match_type)
            for row, score, match_type in self._search(
                query,
                self.repository.list_warehouses(),
                ("warehouse", "warehouse_name"),
                limit,
            )
        ]

    def search_uoms(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return [
            self._uom_result(row, score, match_type)
            for row, score, match_type in self._search(
                query, self.repository.list_uoms(), ("uom",), limit
            )
        ]

    def match_item(self, input_name: str) -> MatchResult:
        """Match item with deterministic priority and avoid unsafe auto-selection."""
        if settings.debug_master_data_match:
            logger.info(
                "[master-data-match-debug] match_item start input=%r normalized=%r",
                input_name,
                self._normalize(input_name),
            )
            logger.info(
                "[master-data-match-debug] match_item query table=erpnext_items fields=item_code,item_name keyword=%r",
                input_name,
            )
        rows = self.repository.list_items()
        exact = self._exact_matches(
            input_name, rows, ("item_code", "item_name"), normalized=False
        )
        if exact:
            return self._item_match_from_candidates(input_name, exact, "已精确匹配")

        normalized = self._exact_matches(
            input_name, rows, ("item_code", "item_name"), normalized=True
        )
        if normalized:
            return self._item_match_from_candidates(
                input_name, normalized, "已标准化后精确匹配"
            )

        candidates = self.search_items(input_name)
        high_confidence = [
            candidate for candidate in candidates if candidate["score"] >= 0.75
        ]
        if not high_confidence:
            if settings.debug_master_data_match:
                logger.info(
                    "[master-data-match-debug] match_item result status=not_found input=%r normalized=%r",
                    input_name,
                    self._normalize(input_name),
                )
            return MatchResult(
                status="not_found", input=input_name, message="未找到匹配商品"
            )
        if len(high_confidence) == 1:
            candidate = high_confidence[0]
            if candidate.get("disabled"):
                return MatchResult(
                    status="disabled",
                    input=input_name,
                    selected=candidate,
                    candidates=high_confidence,
                    message="找到的商品已禁用，不能自动匹配",
                )
            return MatchResult(
                status="matched",
                input=input_name,
                selected=candidate,
                candidates=high_confidence,
                message="已通过包含/模糊规则匹配唯一商品",
            )
        return MatchResult(
            status="ambiguous",
            input=input_name,
            candidates=high_confidence,
            message="找到多个可能商品，请人工确认",
        )
        

    def match_supplier(
        self, input_name: str | None, default_supplier: str | None = None
    ) -> MatchResult:
        effective_input = (
            input_name or default_supplier or settings.default_purchase_supplier
        )
        if settings.debug_master_data_match:
            logger.info(
                "[master-data-match-debug] match_supplier start input=%r normalized=%r",
                input_name,
                self._normalize(input_name or ""),
            )
            logger.info(
                "[master-data-match-debug] match_supplier default_supplier=%r",
                default_supplier or settings.default_purchase_supplier,
            )
            logger.info(
                "[master-data-match-debug] match_supplier special_case other_supplier=%s",
                False,
            )
            if input_name and not effective_input == input_name:
                logger.info(
                    "[master-data-match-debug] match_supplier supplier input=%r replaced_by_default_supplier=%r",
                    input_name,
                    effective_input,
                )
        if not effective_input:
            return MatchResult(
                status="not_found",
                input=input_name,
                message="未提供供应商，且未配置默认供应商",
            )

        rows = self.repository.list_suppliers()
        if settings.debug_master_data_match:
            logger.info(
                "[master-data-match-debug] match_supplier query table=erpnext_suppliers fields=supplier,supplier_name keyword=%r",
                effective_input,
            )
        exact = self._exact_matches(
            effective_input, rows, ("supplier", "supplier_name"), normalized=False
        )
        if not exact:
            exact = self._exact_matches(
                effective_input, rows, ("supplier", "supplier_name"), normalized=True
            )
        if exact:
            result = self._supplier_match_from_candidates(
                input_name, effective_input, exact
            )
            if not input_name and result.status == "matched":
                result.message = "未提供供应商，已使用默认供应商"
            return result

        candidates = self.search_suppliers(effective_input)
        high_confidence = [
            candidate for candidate in candidates if candidate["score"] >= 0.75
        ]
        if not high_confidence:
            message = "默认供应商不存在于缓存" if not input_name else "未找到匹配供应商"
            if settings.debug_master_data_match and message == "默认供应商不存在于缓存":
                logger.info(
                    "[master-data-match-debug] match_supplier default supplier not found default_supplier=%r",
                    effective_input,
                )
            return MatchResult(status="not_found", input=input_name, message=message)
        if len(high_confidence) == 1:
            candidate = high_confidence[0]
            selected = self._supplier_selected(candidate, input_name, effective_input)
            if candidate.get("disabled"):
                return MatchResult(
                    status="disabled",
                    input=input_name,
                    selected=selected,
                    candidates=high_confidence,
                    message="找到的供应商已禁用，不能自动匹配",
                )
            return MatchResult(
                status="matched",
                input=input_name,
                selected=selected,
                candidates=high_confidence,
                message="已通过包含/模糊规则匹配唯一供应商",
            )
        return MatchResult(
            status="ambiguous",
            input=input_name,
            candidates=high_confidence,
            message="找到多个可能供应商，请人工确认",
        )

    def validate_warehouse(self, warehouse: str | None = None) -> ValidationResult:
        effective_warehouse = warehouse or settings.default_purchase_warehouse
        if settings.debug_master_data_match:
            logger.info(
                "[master-data-match-debug] match_warehouse start input=%r normalized=%r",
                warehouse,
                self._normalize(effective_warehouse or ""),
            )
            logger.info(
                "[master-data-match-debug] match_warehouse default_warehouse=%r",
                settings.default_purchase_warehouse,
            )
            logger.info(
                "[master-data-match-debug] match_warehouse query table=erpnext_warehouses fields=warehouse,warehouse_name keyword=%r",
                effective_warehouse,
            )
        if not effective_warehouse:
            return ValidationResult(
                status="validation_failed",
                input=warehouse,
                message="未提供仓库，且未配置默认采购仓库",
            )
        matches = self._exact_matches(
            effective_warehouse,
            self.repository.list_warehouses(),
            ("warehouse", "warehouse_name"),
            normalized=True,
        )
        if not matches:
            return ValidationResult(
                status="validation_failed", input=warehouse, message="仓库不存在于缓存"
            )
        candidates = [self._warehouse_result(row, 1.0, "exact") for row in matches]
        enabled = [
            candidate
            for candidate in candidates
            if not candidate.get("disabled") and not candidate.get("is_group")
        ]
        if len(enabled) == 1:
            return ValidationResult(
                status="matched",
                input=warehouse,
                selected=enabled[0],
                candidates=candidates,
                message="仓库校验通过",
            )
        return ValidationResult(
            status="validation_failed",
            input=warehouse,
            candidates=candidates,
            message="仓库已禁用、为分组仓库或无法唯一确认",
        )

    def validate_uom(self, uom: str) -> ValidationResult:
        if settings.debug_master_data_match:
            logger.info(
                "[master-data-match-debug] match_uom start input=%r normalized=%r",
                uom,
                self._normalize(uom),
            )
            logger.info(
                "[master-data-match-debug] match_uom alias input=%r mapped=%r",
                uom,
                uom,
            )
            logger.info(
                "[master-data-match-debug] match_uom query table=erpnext_uoms fields=uom keyword=%r",
                uom,
            )
        matches = self._exact_matches(
            uom, self.repository.list_uoms(), ("uom",), normalized=True
        )
        if not matches:
            return ValidationResult(
                status="validation_failed", input=uom, message="单位不存在于缓存"
            )
        candidates = [self._uom_result(row, 1.0, "exact") for row in matches]
        enabled = [
            candidate for candidate in candidates if candidate.get("enabled", True)
        ]
        if len(enabled) == 1:
            return ValidationResult(
                status="matched",
                input=uom,
                selected=enabled[0],
                candidates=candidates,
                message="单位校验通过",
            )
        return ValidationResult(
            status="validation_failed",
            input=uom,
            candidates=candidates,
            message="单位已禁用或无法唯一确认",
        )

    def _item_match_from_candidates(
        self, input_name: str, rows: list[dict[str, Any]], message: str
    ) -> MatchResult:
        if settings.debug_master_data_match:
            logger.info(
                "[master-data-match-debug] match_item candidates_count=%s",
                len(rows),
            )
        candidates = [self._item_result(row, 1.0, "exact") for row in rows]
        if settings.debug_master_data_match:
            for i, candidate in enumerate(candidates[:5]):
                logger.info(
                    "[master-data-match-debug] match_item candidate[%s] name=%r item_code=%r item_name=%r",
                    i,
                    candidate.get("item_name"),
                    candidate.get("item_code"),
                    candidate.get("item_name"),
                )
        enabled = [
            candidate for candidate in candidates if not candidate.get("disabled")
        ]
        if len(candidates) == 1 and candidates[0].get("disabled"):
            return MatchResult(
                status="disabled",
                input=input_name,
                selected=candidates[0],
                candidates=candidates,
                message="商品已禁用，不能自动匹配",
            )
        if len(enabled) == 1 and len(candidates) == 1:
            if settings.debug_master_data_match:
                logger.info(
                    "[master-data-match-debug] match_item result status=matched item_code=%r item_name=%r",
                    enabled[0].get("item_code"),
                    enabled[0].get("item_name"),
                )
            return MatchResult(
                status="matched",
                input=input_name,
                selected=enabled[0],
                candidates=candidates,
                message=message,
            )
        return MatchResult(
            status="ambiguous",
            input=input_name,
            candidates=candidates,
            message="找到多个可能商品，请人工确认",
        )

    def _supplier_match_from_candidates(
        self, raw_input: str | None, effective_input: str, rows: list[dict[str, Any]]
    ) -> MatchResult:
        if settings.debug_master_data_match:
            logger.info(
                "[master-data-match-debug] match_supplier candidates_count=%s",
                len(rows),
            )
        candidates = [self._supplier_result(row, 1.0, "exact") for row in rows]
        if settings.debug_master_data_match:
            for i, candidate in enumerate(candidates[:5]):
                logger.info(
                    "[master-data-match-debug] match_supplier candidate[%s] name=%r supplier_name=%r",
                    i,
                    candidate.get("supplier"),
                    candidate.get("supplier_name"),
                )
        enabled = [
            candidate for candidate in candidates if not candidate.get("disabled")
        ]
        if len(candidates) == 1 and candidates[0].get("disabled"):
            selected = self._supplier_selected(
                candidates[0], raw_input, effective_input
            )
            return MatchResult(
                status="disabled",
                input=raw_input,
                selected=selected,
                candidates=candidates,
                message="供应商已禁用，不能自动匹配",
            )
        if len(enabled) == 1 and len(candidates) == 1:
            if settings.debug_master_data_match:
                logger.info(
                    "[master-data-match-debug] match_supplier result status=matched supplier_name=%r",
                    (enabled[0].get("supplier_name") or enabled[0].get("supplier")),
                )
            return MatchResult(
                status="matched",
                input=raw_input,
                selected=self._supplier_selected(
                    enabled[0], raw_input, effective_input
                ),
                candidates=candidates,
                message="已精确匹配供应商",
            )
        return MatchResult(
            status="ambiguous",
            input=raw_input,
            candidates=candidates,
            message="找到多个可能供应商，请人工确认",
        )

    def _search(
        self,
        query: str,
        rows: list[dict[str, Any]],
        fields: tuple[str, ...],
        limit: int,
    ) -> list[tuple[dict[str, Any], float, str]]:
        normalized_query = self._normalize(query)
        if not normalized_query:
            return []
        scored = []
        for row in rows:
            score, match_type = self._row_score(normalized_query, row, fields)
            if score > 0:
                scored.append((row, score, match_type))
        scored.sort(key=lambda item: (-item[1], self._display_value(item[0], fields)))
        return scored[:limit]

    def _row_score(
        self, normalized_query: str, row: dict[str, Any], fields: tuple[str, ...]
    ) -> tuple[float, str]:
        best_score = 0.0
        best_type = "fuzzy"
        for field in fields:
            value = row.get(field)
            if not value:
                continue
            normalized_value = self._normalize(str(value))
            if normalized_query == normalized_value:
                return 1.0, "exact"
            if (
                normalized_query in normalized_value
                or normalized_value in normalized_query
            ):
                shorter = min(len(normalized_query), len(normalized_value))
                longer = max(len(normalized_query), len(normalized_value))
                score = max(0.82, shorter / longer if longer else 0.0)
                match_type = "partial"
            else:
                score = SequenceMatcher(
                    None, normalized_query, normalized_value
                ).ratio()
                match_type = "fuzzy"
            if score > best_score:
                best_score = score
                best_type = match_type
        return (
            (round(best_score, 4), best_type) if best_score >= 0.5 else (0.0, best_type)
        )

    def _exact_matches(
        self,
        query: str,
        rows: list[dict[str, Any]],
        fields: tuple[str, ...],
        normalized: bool,
    ) -> list[dict[str, Any]]:
        if normalized:
            normalized_query = self._normalize(query)
            return [
                row
                for row in rows
                if any(
                    self._normalize(str(row.get(field) or "")) == normalized_query
                    for field in fields
                )
            ]
        return [
            row
            for row in rows
            if any(str(row.get(field) or "") == query for field in fields)
        ]

    def _item_result(
        self, row: dict[str, Any], score: float, match_type: str
    ) -> dict[str, Any]:
        return {
            "item_code": row["item_code"],
            "item_name": row.get("item_name"),
            "stock_uom": row.get("stock_uom"),
            "disabled": self._is_truthy(row.get("disabled")),
            "match_type": match_type,
            "score": score,
        }

    def _supplier_result(
        self, row: dict[str, Any], score: float, match_type: str
    ) -> dict[str, Any]:
        return {
            "supplier": row["supplier"],
            "supplier_name": row.get("supplier_name"),
            "disabled": self._is_truthy(row.get("disabled")),
            "match_type": match_type,
            "score": score,
        }

    def _warehouse_result(
        self, row: dict[str, Any], score: float, match_type: str
    ) -> dict[str, Any]:
        return {
            "warehouse": row["warehouse"],
            "warehouse_name": row.get("warehouse_name"),
            "is_group": self._is_truthy(row.get("is_group")),
            "disabled": self._is_truthy(row.get("disabled")),
            "match_type": match_type,
            "score": score,
        }

    def _uom_result(
        self, row: dict[str, Any], score: float, match_type: str
    ) -> dict[str, Any]:
        enabled = (
            True if row.get("enabled") is None else self._is_truthy(row.get("enabled"))
        )
        return {
            "uom": row["uom"],
            "enabled": enabled,
            "match_type": match_type,
            "score": score,
        }

    def _supplier_selected(
        self, candidate: dict[str, Any], raw_input: str | None, effective_input: str
    ) -> dict[str, Any]:
        return {
            "raw_supplier_name": raw_input,
            "input_supplier_name": effective_input,
            "supplier": candidate["supplier"],
            "erp_supplier_name": candidate.get("supplier_name")
            or candidate["supplier"],
        }

    def _display_value(self, row: dict[str, Any], fields: tuple[str, ...]) -> str:
        return str(row.get(fields[0]) or "")

    def _normalize(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)
        return "".join(normalized.casefold().split())

    def _is_truthy(self, value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes"}
        return bool(value)

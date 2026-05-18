from typing import Any, Literal

from pydantic import BaseModel, Field

MatchStatus = Literal["matched", "ambiguous", "not_found", "disabled"]
ValidationStatus = Literal["matched", "validation_failed"]


class SearchResult(BaseModel):
    match_type: str
    score: float = Field(ge=0, le=1)


class ItemSearchResult(SearchResult):
    item_code: str
    item_name: str | None = None
    stock_uom: str | None = None
    disabled: bool = False


class SupplierSearchResult(SearchResult):
    supplier: str
    supplier_name: str | None = None
    disabled: bool = False


class WarehouseSearchResult(SearchResult):
    warehouse: str
    warehouse_name: str | None = None
    is_group: bool = False
    disabled: bool = False


class UomSearchResult(SearchResult):
    uom: str
    enabled: bool = True


class ItemSearchResponse(BaseModel):
    query: str
    results: list[ItemSearchResult]


class SupplierSearchResponse(BaseModel):
    query: str
    results: list[SupplierSearchResult]


class WarehouseSearchResponse(BaseModel):
    query: str
    results: list[WarehouseSearchResult]


class UomSearchResponse(BaseModel):
    query: str
    results: list[UomSearchResult]


class MatchResult(BaseModel):
    status: MatchStatus
    input: str | None = None
    selected: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    message: str


class ValidationResult(BaseModel):
    status: ValidationStatus
    input: str | None = None
    selected: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    message: str

from fastapi import APIRouter, Query

from app.config import settings
from app.repositories.master_data_cache_repository import MasterDataCacheRepository
from app.schemas.master_data_match import (
    ItemSearchResponse,
    SupplierSearchResponse,
    UomSearchResponse,
    WarehouseSearchResponse,
)
from app.services.master_data_match_service import MasterDataMatchService

router = APIRouter(prefix="/api/master-data", tags=["master-data"])


def _service() -> MasterDataMatchService:
    return MasterDataMatchService(
        MasterDataCacheRepository(settings.master_data_cache_db)
    )


@router.get("/items/search", response_model=ItemSearchResponse)
def search_items(
    q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)
):
    return {"query": q, "results": _service().search_items(q, limit=limit)}


@router.get("/suppliers/search", response_model=SupplierSearchResponse)
def search_suppliers(
    q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)
):
    return {"query": q, "results": _service().search_suppliers(q, limit=limit)}


@router.get("/warehouses/search", response_model=WarehouseSearchResponse)
def search_warehouses(
    q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)
):
    return {"query": q, "results": _service().search_warehouses(q, limit=limit)}


@router.get("/uoms/search", response_model=UomSearchResponse)
def search_uoms(
    q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)
):
    return {"query": q, "results": _service().search_uoms(q, limit=limit)}

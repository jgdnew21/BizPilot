from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.integrations.erpnext.client import ERPNextAPIError
from app.services.master_data_sync_service import MasterDataSyncService

router = APIRouter(prefix="/api/erpnext/sync", tags=["erpnext-sync"])


class SyncResponse(BaseModel):
    status: str
    summary: dict[str, dict[str, int]]


def get_sync_service() -> MasterDataSyncService:
    return MasterDataSyncService()


def _run_sync(sync_name: str, sync_func) -> SyncResponse:  # type: ignore[no-untyped-def]
    try:
        summary = {sync_name: sync_func()}
        return SyncResponse(status="success", summary=summary)
    except ERPNextAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/master-data", response_model=SyncResponse)
def sync_master_data() -> SyncResponse:
    try:
        summary = get_sync_service().sync_master_data()
        return SyncResponse(status="success", summary=summary)
    except ERPNextAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/items", response_model=SyncResponse)
def sync_items() -> SyncResponse:
    return _run_sync("items", lambda: get_sync_service().sync_items())


@router.post("/suppliers", response_model=SyncResponse)
def sync_suppliers() -> SyncResponse:
    return _run_sync("suppliers", lambda: get_sync_service().sync_suppliers())


@router.post("/warehouses", response_model=SyncResponse)
def sync_warehouses() -> SyncResponse:
    return _run_sync("warehouses", lambda: get_sync_service().sync_warehouses())


@router.post("/uoms", response_model=SyncResponse)
def sync_uoms() -> SyncResponse:
    return _run_sync("uoms", lambda: get_sync_service().sync_uoms())

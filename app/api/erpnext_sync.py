from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.integrations.erpnext_client import ErpnextApiError, ErpnextClient, ErpnextConnectionError
from app.repositories.master_data_cache_repository import MasterDataCacheRepository
from app.services.master_data_sync_service import MasterDataSyncService

router = APIRouter(prefix="/api/erpnext/sync", tags=["erpnext-sync"])


def _service() -> MasterDataSyncService:
    return MasterDataSyncService(
        client=ErpnextClient(settings.erpnext_base_url, settings.erpnext_api_key, settings.erpnext_api_secret),
        repository=MasterDataCacheRepository(settings.master_data_cache_db),
        company=settings.erpnext_company,
    )


def _summary(result: dict | object) -> dict:
    if isinstance(result, dict):
        return {key: value.to_dict() for key, value in result.items()}
    return result.to_dict()


def _run_sync(sync_fn: Callable[[], dict | object]):
    try:
        return {"status": "success", "summary": _summary(sync_fn())}
    except ErpnextConnectionError as exc:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": "ERPNext connection failed", "url": exc.url, "error": exc.message},
        ) from exc
    except ErpnextApiError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "message": "ERPNext API error",
                "erpnext_status_code": exc.status_code,
                "url": exc.url,
                "response": exc.response_text_summary,
            },
        ) from exc


@router.post("/master-data")
def sync_master_data():
    return _run_sync(_service().sync_all)


@router.post("/items")
def sync_items():
    return _run_sync(_service().sync_items)


@router.post("/suppliers")
def sync_suppliers():
    return _run_sync(_service().sync_suppliers)


@router.post("/warehouses")
def sync_warehouses():
    return _run_sync(_service().sync_warehouses)


@router.post("/uoms")
def sync_uoms():
    return _run_sync(_service().sync_uoms)

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.integrations.erpnext_client import ErpnextClient

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "bizpilot", "version": "0.2"}


@router.get("/health/ready")
def ready():
    checks = {"settings": "ok"}

    snapshot_dir = Path(settings.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    checks["snapshot_dir"] = "ok" if snapshot_dir.exists() else "error"

    master_data_dir = Path(settings.master_data_dir)
    checks["master_data_dir"] = "ok" if master_data_dir.exists() else "error"

    files = {
        "items_json": master_data_dir / "items.json",
        "suppliers_json": master_data_dir / "suppliers.json",
        "warehouses_json": master_data_dir / "warehouses.json",
    }
    for key, file_path in files.items():
        checks[key] = "ok" if file_path.exists() else "error"

    failed = [name for name, result in checks.items() if result != "ok"]
    if failed:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks, "failed": failed})

    return {"status": "ready", "checks": checks}


@router.get("/health/erpnext")
def erpnext_health():
    client = ErpnextClient(settings.erpnext_base_url, settings.erpnext_api_key, settings.erpnext_api_secret)
    ok, payload = client.ping()
    if ok:
        return {"status": "ok", "erpnext": "reachable", "user": payload.get("user")}
    raise HTTPException(status_code=503, detail={"status": "error", "erpnext": "unreachable", "message": payload.get("message", "unknown error")})

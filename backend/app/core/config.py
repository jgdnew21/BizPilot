import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _clean_url(value: str) -> str:
    return value.rstrip("/").strip()


ERPNEXT_BASE_URL = _clean_url(os.getenv("ERPNEXT_BASE_URL", ""))
ERPNEXT_API_KEY = os.getenv("ERPNEXT_API_KEY", "").strip()
ERPNEXT_API_SECRET = os.getenv("ERPNEXT_API_SECRET", "").strip()

SNAPSHOT_DIR = Path(os.getenv("SNAPSHOT_DIR", "./app/data/snapshots"))
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_WAREHOUSE = os.getenv("DEFAULT_WAREHOUSE", "南宁仓 - 艾达D").strip()
DEFAULT_COMPANY = os.getenv("DEFAULT_COMPANY", "艾达智境 (Demo)").strip()


def validate_settings() -> None:
    missing = []

    if not ERPNEXT_BASE_URL:
        missing.append("ERPNEXT_BASE_URL")
    if not ERPNEXT_API_KEY:
        missing.append("ERPNEXT_API_KEY")
    if not ERPNEXT_API_SECRET:
        missing.append("ERPNEXT_API_SECRET")

    if missing:
        raise ValueError(f"Missing required settings: {', '.join(missing)}")
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import erpnext_sync
from app.integrations.erpnext.client import ERPNextAPIError


class FakeService:
    def sync_master_data(self):  # type: ignore[no-untyped-def]
        return {
            "items": {"fetched": 2, "upserted": 2},
            "suppliers": {"fetched": 1, "upserted": 1},
            "warehouses": {"fetched": 1, "upserted": 1},
            "uoms": {"fetched": 3, "upserted": 3},
        }

    def sync_items(self):  # type: ignore[no-untyped-def]
        return {"fetched": 2, "upserted": 2}


class ErrorService:
    def sync_items(self):  # type: ignore[no-untyped-def]
        raise ERPNextAPIError("ERPNext API error for Item: HTTP 401: Invalid API key")


def test_master_data_api_returns_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(erpnext_sync, "get_sync_service", lambda: FakeService())

    response = erpnext_sync.sync_master_data()

    assert response.model_dump() == {
        "status": "success",
        "summary": {
            "items": {"fetched": 2, "upserted": 2},
            "suppliers": {"fetched": 1, "upserted": 1},
            "warehouses": {"fetched": 1, "upserted": 1},
            "uoms": {"fetched": 3, "upserted": 3},
        },
    }


def test_sync_api_returns_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(erpnext_sync, "get_sync_service", lambda: ErrorService())

    with pytest.raises(HTTPException) as exc_info:
        erpnext_sync.sync_items()

    assert exc_info.value.status_code == 502
    assert "Invalid API key" in str(exc_info.value.detail)

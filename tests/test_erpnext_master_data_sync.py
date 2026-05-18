import json
from urllib.parse import unquote

import pytest
import requests
from unittest.mock import Mock

from fastapi import HTTPException

from app.config import settings
from app.integrations.erpnext_client import ErpnextApiError, ErpnextClient, ErpnextConnectionError
from app.repositories.master_data_cache_repository import MasterDataCacheRepository
from app.services.master_data_sync_service import MasterDataSyncService


def test_erpnext_client_fetch_all_paginates_and_sends_fields(monkeypatch):
    responses = [
        Mock(status_code=200, url="http://erp/api/resource/Item", json=lambda: {"data": [{"name": "A"}, {"name": "B"}]}),
        Mock(status_code=200, url="http://erp/api/resource/Item", json=lambda: {"data": [{"name": "C"}]}),
    ]
    get = Mock(side_effect=responses)
    monkeypatch.setattr("app.integrations.erpnext_client.requests.get", get)

    client = ErpnextClient("http://erp/", "key", "secret")
    rows = client.fetch_all("Item", ["name", "item_code"], filters={"disabled": 0}, page_length=2)

    assert rows == [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    assert get.call_count == 2
    first_params = get.call_args_list[0].kwargs["params"]
    second_params = get.call_args_list[1].kwargs["params"]
    assert json.loads(unquote(first_params["fields"])) == ["name", "item_code"]
    assert json.loads(unquote(first_params["filters"])) == {"disabled": 0}
    assert first_params["limit_start"] == 0
    assert second_params["limit_start"] == 2
    assert client.headers["Authorization"] == "token key:secret"


def test_erpnext_client_fetch_all_raises_clear_api_error(monkeypatch):
    response = Mock(status_code=403, url="http://erp/api/resource/Item", text="bad key")
    monkeypatch.setattr("app.integrations.erpnext_client.requests.get", Mock(return_value=response))

    with pytest.raises(ErpnextApiError) as exc_info:
        ErpnextClient("http://erp", "bad", "secret").fetch_all("Item", ["name"])

    assert exc_info.value.status_code == 403
    assert "bad key" in exc_info.value.response_text_summary


def test_erpnext_client_fetch_all_raises_clear_connection_error(monkeypatch):
    monkeypatch.setattr("app.integrations.erpnext_client.requests.get", Mock(side_effect=requests.ConnectionError("offline")))

    with pytest.raises(ErpnextConnectionError) as exc_info:
        ErpnextClient("http://erp", "key", "secret").fetch_all("Item", ["name"])

    assert "offline" in exc_info.value.message


def test_master_data_sync_service_syncs_all_and_upserts_without_duplicates(tmp_path):
    db_path = tmp_path / "master_data.sqlite3"
    repository = MasterDataCacheRepository(str(db_path))

    class FakeClient:
        def fetch_all(self, doctype, fields, filters=None):
            if doctype == "Item":
                return [{"name": "ITEM-1", "item_code": "ITEM-1", "item_name": "Rice", "stock_uom": "Kg", "modified": "2026-01-01"}]
            if doctype == "Supplier":
                return [{"name": "SUP-1", "supplier_name": "Supplier One", "modified": "2026-01-01"}]
            if doctype == "Warehouse":
                assert filters == {"company": "BizPilot Co"}
                return [{"name": "WH-1", "warehouse_name": "Main WH", "company": "BizPilot Co", "modified": "2026-01-01"}]
            if doctype == "UOM":
                return [{"name": "Kg", "enabled": 1, "modified": "2026-01-01"}]
            return []

    service = MasterDataSyncService(FakeClient(), repository, company="BizPilot Co")
    first_summary = service.sync_all()
    second_summary = service.sync_all()

    assert first_summary["items"].to_dict() == {"fetched": 1, "upserted": 1}
    assert second_summary["items"].to_dict() == {"fetched": 1, "upserted": 1}
    assert repository.count("erpnext_items") == 1
    assert repository.count("erpnext_suppliers") == 1
    assert repository.count("erpnext_warehouses") == 1
    assert repository.count("erpnext_uoms") == 1


def test_sync_api_returns_summary_and_writes_cache(tmp_path, monkeypatch):
    db_path = tmp_path / "api_cache.sqlite3"
    old_db, old_company = settings.master_data_cache_db, settings.erpnext_company
    settings.master_data_cache_db = str(db_path)
    settings.erpnext_company = "BizPilot Co"

    def fake_fetch_all(self, doctype, fields, filters=None):
        if doctype == "Item":
            return [{"name": "ITEM-1", "item_code": "ITEM-1", "item_name": "Rice"}]
        if doctype == "Supplier":
            return [{"name": "SUP-1", "supplier_name": "Supplier One"}]
        if doctype == "Warehouse":
            return [{"name": "WH-1", "warehouse_name": "Main WH", "company": "BizPilot Co"}]
        if doctype == "UOM":
            return [{"name": "Kg", "enabled": 1}]
        return []

    monkeypatch.setattr(ErpnextClient, "fetch_all", fake_fetch_all)
    try:
        from app.api.erpnext_sync import sync_master_data

        response = sync_master_data()
    finally:
        settings.master_data_cache_db = old_db
        settings.erpnext_company = old_company

    assert response == {
        "status": "success",
        "summary": {
            "items": {"fetched": 1, "upserted": 1},
            "suppliers": {"fetched": 1, "upserted": 1},
            "warehouses": {"fetched": 1, "upserted": 1},
            "uoms": {"fetched": 1, "upserted": 1},
        },
    }
    assert MasterDataCacheRepository(str(db_path)).count("erpnext_items") == 1


def test_sync_api_returns_clear_error_on_erpnext_failure(tmp_path, monkeypatch):
    old_db = settings.master_data_cache_db
    settings.master_data_cache_db = str(tmp_path / "api_error_cache.sqlite3")

    def raise_error(self, doctype, fields, filters=None):
        raise ErpnextApiError(401, "http://erp/api/resource/Item", "invalid api key")

    monkeypatch.setattr(ErpnextClient, "fetch_all", raise_error)
    try:
        from app.api.erpnext_sync import sync_items

        with pytest.raises(HTTPException) as exc_info:
            sync_items()
        response = exc_info.value
    finally:
        settings.master_data_cache_db = old_db

    assert response.status_code == 502
    assert response.detail["message"] == "ERPNext API error"
    assert response.detail["erpnext_status_code"] == 401
    assert response.detail["response"] == "invalid api key"

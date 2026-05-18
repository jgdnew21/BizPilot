from __future__ import annotations

import json

import pytest
import requests

from app.integrations.erpnext.client import ERPNextAPIError, ERPNextMasterDataClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def test_fetch_all_reads_all_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_get(url, params, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append(params)
        start = params["limit_start"]
        if start == 0:
            return FakeResponse(200, {"data": [{"name": "A"}, {"name": "B"}]})
        return FakeResponse(200, {"data": [{"name": "C"}]})

    monkeypatch.setattr(requests, "get", fake_get)
    client = ERPNextMasterDataClient(
        base_url="http://erp.test",
        api_key="key",
        api_secret="secret",
        page_size=2,
    )

    rows = client.fetch_all("Item", ["name", "item_code"], {"disabled": 0})

    assert rows == [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    assert [call["limit_start"] for call in calls] == [0, 2]
    assert json.loads(calls[0]["fields"]) == ["name", "item_code"]
    assert json.loads(calls[0]["filters"]) == {"disabled": 0}


def test_fetch_all_raises_clear_error_on_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url, params, headers, timeout):  # type: ignore[no-untyped-def]
        return FakeResponse(401, {"exception": "Invalid API key"})

    monkeypatch.setattr(requests, "get", fake_get)
    client = ERPNextMasterDataClient(base_url="http://erp.test", api_key="bad", api_secret="bad")

    with pytest.raises(ERPNextAPIError, match="HTTP 401: Invalid API key"):
        client.fetch_all("Supplier", ["name"])

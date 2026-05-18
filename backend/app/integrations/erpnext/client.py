from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import requests

from app.core.config import ERPNEXT_API_KEY, ERPNEXT_API_SECRET, ERPNEXT_BASE_URL


class ERPNextAPIError(Exception):
    """Raised when ERPNext cannot return a successful API response."""


class ERPNextMasterDataClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        timeout: int = 30,
        page_size: int = 500,
    ) -> None:
        self.base_url = (base_url or ERPNEXT_BASE_URL).rstrip("/")
        self.api_key = api_key or ERPNEXT_API_KEY
        self.api_secret = api_secret or ERPNEXT_API_SECRET
        self.timeout = timeout
        self.page_size = page_size
        missing = []
        if not self.base_url:
            missing.append("ERPNEXT_BASE_URL")
        if not self.api_key:
            missing.append("ERPNEXT_API_KEY")
        if not self.api_secret:
            missing.append("ERPNEXT_API_SECRET")
        if missing:
            raise ValueError(f"Missing required settings: {', '.join(missing)}")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self.api_key}:{self.api_secret}",
            "Content-Type": "application/json",
        }

    def fetch_all(
        self,
        doctype: str,
        fields: list[str],
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        limit_start = 0

        while True:
            page = self._fetch_page(
                doctype=doctype,
                fields=fields,
                filters=filters,
                limit_start=limit_start,
            )
            results.extend(page)
            if len(page) < self.page_size:
                break
            limit_start += self.page_size

        return results

    def _fetch_page(
        self,
        doctype: str,
        fields: list[str],
        filters: dict[str, Any] | None,
        limit_start: int,
    ) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/resource/{quote(doctype)}"
        params: dict[str, Any] = {
            "fields": json.dumps(fields),
            "limit_start": limit_start,
            "limit_page_length": self.page_size,
        }
        if filters:
            params["filters"] = json.dumps(filters)

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ERPNextAPIError(f"ERPNext connection failed for {doctype}: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ERPNextAPIError(f"ERPNext returned non-JSON response for {doctype}: {response.text}") from exc

        if response.status_code != 200:
            message = payload.get("exception") or payload.get("_server_messages") or payload.get("message") or payload
            raise ERPNextAPIError(f"ERPNext API error for {doctype}: HTTP {response.status_code}: {message}")

        data = payload.get("data", [])
        if data is None:
            return []
        if not isinstance(data, list):
            raise ERPNextAPIError(f"ERPNext returned invalid data for {doctype}: expected list")
        return data

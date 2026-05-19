import json
import logging
from typing import Any

import requests


logger = logging.getLogger(__name__)


class ErpnextApiError(Exception):
    def __init__(self, status_code: int, url: str, response_text_summary: str):
        self.status_code = status_code
        self.url = url
        self.response_text_summary = response_text_summary
        super().__init__(f"ERPNext API error {status_code} for {url}: {response_text_summary}")


class ErpnextConnectionError(Exception):
    def __init__(self, url: str, message: str):
        self.url = url
        self.message = message
        super().__init__(f"ERPNext connection failed for {url}: {message}")


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"token {api_key}:{api_secret}", "Content-Type": "application/json"}

    def fetch_all(
        self,
        doctype: str,
        fields: list[str],
        filters: dict[str, Any] | None = None,
        page_length: int = 500,
    ) -> list[dict[str, Any]]:
        """Fetch all rows for an ERPNext DocType using REST API pagination."""
        rows: list[dict[str, Any]] = []
        limit_start = 0
        while True:
            page = self._fetch_page(doctype, fields, filters, limit_start, page_length)
            rows.extend(page)
            if len(page) < page_length:
                return rows
            limit_start += page_length

    def _fetch_page(
        self,
        doctype: str,
        fields: list[str],
        filters: dict[str, Any] | None,
        limit_start: int,
        page_length: int,
    ) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/resource/{doctype}"
        params: dict[str, str | int] = {
            "fields": json.dumps(fields),
            "limit_start": limit_start,
            "limit_page_length": page_length,
        }
        if filters:
            params["filters"] = json.dumps(filters)
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        except requests.RequestException as exc:
            logger.error("ERPNext fetch failed: url=%s error=%s", url, exc)
            raise ErpnextConnectionError(url, str(exc)) from exc
        if resp.status_code != 200:
            response_text_summary = (resp.text or "")[:1000].strip() or "(empty response body)"
            logger.error(
                "ERPNext fetch failed: status_code=%s url=%s response_text=%s",
                resp.status_code,
                resp.url,
                response_text_summary,
            )
            raise ErpnextApiError(resp.status_code, resp.url, response_text_summary)
        try:
            body = resp.json()
        except ValueError as exc:
            raise ErpnextApiError(resp.status_code, resp.url, "invalid JSON response") from exc
        data = body.get("data", [])
        if data is None:
            return []
        if not isinstance(data, list):
            raise ErpnextApiError(resp.status_code, resp.url, "ERPNext response data is not a list")
        return data

    def create_material_request(self, payload: dict) -> str:
        resp = requests.post(f"{self.base_url}/api/resource/Material Request", json=payload, headers=self.headers, timeout=20)
        if resp.status_code >= 400:
            response_text_summary = (resp.text or "")[:1000].strip() or "(empty response body)"
            logger.error(
                "ERPNext create Material Request failed: status_code=%s url=%s response_text=%s",
                resp.status_code,
                resp.url,
                response_text_summary,
            )
            raise ErpnextApiError(resp.status_code, resp.url, response_text_summary)
        body = resp.json()
        return body["data"]["name"]

    def ping(self) -> tuple[bool, dict]:
        try:
            resp = requests.get(
                f"{self.base_url}/api/method/frappe.auth.get_logged_user",
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            body = resp.json()
            user = body.get("message") or body.get("data")
            return True, {"user": user}
        except requests.RequestException as exc:
            return False, {"message": str(exc)}
        except ValueError:
            return False, {"message": "invalid ERPNext response"}

    def create_purchase_receipt(self, payload: dict) -> str:
        resp = requests.post(
            f"{self.base_url}/api/resource/Purchase Receipt",
            json=payload,
            headers=self.headers,
            timeout=20,
        )
        if resp.status_code >= 400:
            response_text_summary = (resp.text or "")[:1000].strip() or "(empty response body)"
            logger.error(
                "ERPNext create Purchase Receipt failed: status_code=%s url=%s response_text=%s",
                resp.status_code,
                resp.url,
                response_text_summary,
            )
            raise ErpnextApiError(resp.status_code, resp.url, response_text_summary)
        body = resp.json()
        return body["data"]["name"]

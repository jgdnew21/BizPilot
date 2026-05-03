from typing import Any

import requests

from app.core.config import (
    DEFAULT_WAREHOUSE,
    ERPNEXT_API_KEY,
    ERPNEXT_API_SECRET,
    ERPNEXT_BASE_URL,
    validate_settings,
)


class ERPNextError(Exception):
    pass


class ERPNextClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = (base_url or ERPNEXT_BASE_URL).rstrip("/")
        self.api_key = api_key or ERPNEXT_API_KEY
        self.api_secret = api_secret or ERPNEXT_API_SECRET
        self.timeout = timeout

        validate_settings()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self.api_key}:{self.api_secret}",
            "Content-Type": "application/json",
        }
    
    def create_material_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        payload example:
        {
        "material_request_type": "Purchase",
        "schedule_date": "2026-04-24",
        "items": [
            {"item_code": "002130", "qty": 80, "uom": "斤"},
            {"item_code": "002132", "qty": 10, "uom": "个"}
        ]
        }
        """

        items = []

        for item in payload["items"]:
            row = {
                "item_code": item["item_code"],
                "qty": item["qty"],
                "schedule_date": payload["schedule_date"],
            }

            if item.get("uom"):
                row["uom"] = item["uom"]

            items.append(row)

        body = {
            "material_request_type": "Purchase",
            "schedule_date": payload["schedule_date"],
            "items": items,
        }

        url = f"{self.base_url}/api/resource/Material%20Request"
        resp = requests.post(url, json=body, headers=self.headers, timeout=self.timeout)

        try:
            data = resp.json()
        except Exception as exc:
            raise ERPNextError(f"ERPNext returned non-JSON response: {resp.text}") from exc

        if resp.ok and "data" in data:
            return {
                "success": True,
                "mr_no": data["data"]["name"],
                "raw": data["data"],
            }

        raise ERPNextError(
            data.get("exception")
            or data.get("_server_messages")
            or str(data)
        )


    def create_purchase_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        payload example:
        {
          "supplier": "采无忧供应有限公司",
          "schedule_date": "2026-04-24",
          "warehouse": "南宁仓 - 艾达D",
          "items": [
            {"item_code": "002130", "qty": 80, "uom": "斤"},
            {"item_code": "002132", "qty": 10, "uom": "个"}
          ]
        }
        """
        warehouse = payload.get("warehouse") or DEFAULT_WAREHOUSE
        items: list[dict[str, Any]] = []

        for item in payload["items"]:
            row = {
                "item_code": item["item_code"],
                "qty": item["qty"],
                "warehouse": warehouse,
            }

            if item.get("uom"):
                row["uom"] = item["uom"]

            items.append(row)

        body = {
            "supplier": payload["supplier"],
            "schedule_date": payload["schedule_date"],
            "items": items,
        }

        url = f"{self.base_url}/api/resource/Purchase%20Order"
        resp = requests.post(url, json=body, headers=self.headers, timeout=self.timeout)

        try:
            data = resp.json()
        except Exception as exc:
            raise ERPNextError(f"ERPNext returned non-JSON response: {resp.text}") from exc

        if resp.ok and "data" in data:
            return {
                "success": True,
                "po_no": data["data"]["name"],
                "raw": data["data"],
            }

        raise ERPNextError(
            data.get("exception")
            or data.get("_server_messages")
            or str(data)
        )


if __name__ == "__main__":
    client = ERPNextClient()
    result = client.create_purchase_order(
        {
            "supplier": "采无忧供应有限公司",
            "schedule_date": "2026-04-24",
            "warehouse": "南宁仓 - 艾达D",
            "items": [
                {"item_code": "002130", "qty": 80, "uom": "斤"},
                {"item_code": "002132", "qty": 10, "uom": "个"},
                {"item_code": "002136", "qty": 100, "uom": "个"},
            ],
        }
    )
    print(result)
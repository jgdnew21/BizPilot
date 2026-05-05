import logging

import requests


logger = logging.getLogger(__name__)


class ErpnextApiError(Exception):
    def __init__(self, status_code: int, url: str, response_text_summary: str):
        self.status_code = status_code
        self.url = url
        self.response_text_summary = response_text_summary
        super().__init__(f"ERPNext API error {status_code} for {url}: {response_text_summary}")


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"token {api_key}:{api_secret}", "Content-Type": "application/json"}

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

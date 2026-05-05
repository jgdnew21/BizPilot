import requests


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"token {api_key}:{api_secret}", "Content-Type": "application/json"}

    def create_material_request(self, payload: dict) -> str:
        resp = requests.post(f"{self.base_url}/api/resource/Material Request", json=payload, headers=self.headers, timeout=20)
        resp.raise_for_status()
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

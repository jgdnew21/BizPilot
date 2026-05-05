from __future__ import annotations

import json

import requests

from app.config import settings


class LlmClientError(Exception):
    """Base error for LLM client."""


class LlmRequestError(LlmClientError):
    """Raised when the upstream LLM request fails."""


class LlmTimeoutError(LlmClientError):
    """Raised when LLM request times out."""


class LlmOutputParseError(LlmClientError):
    """Raised when LLM output cannot be parsed to JSON."""


class LlmClient:
    def __init__(self) -> None:
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout_seconds = settings.llm_timeout_seconds

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.Timeout as exc:
            raise LlmTimeoutError("LLM request timed out.") from exc
        except requests.RequestException as exc:
            raise LlmRequestError(f"LLM request failed: {exc.__class__.__name__}") from exc

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmOutputParseError("LLM response format is invalid.") from exc

        try:
            return json.loads(content)
        except (TypeError, ValueError) as exc:
            raise LlmOutputParseError("LLM output is not valid JSON.") from exc

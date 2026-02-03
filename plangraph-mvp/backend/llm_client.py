from __future__ import annotations

import json
import os
from typing import Any

import httpx

DEFAULT_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
DEFAULT_API_KEY = os.getenv("LLM_API_KEY", "ollama")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "llama3.1")


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or DEFAULT_API_KEY
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout or float(os.getenv("LLM_TIMEOUT", "12"))
        self.retries = retries or int(os.getenv("LLM_MAX_RETRIES", "2"))

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/chat/completions"
        last_error: Exception | None = None
        for _ in range(self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_error = exc
                continue
        raise RuntimeError(f"LLM request failed: {last_error}")

    def parse_plan(self, text: str, schema_hint: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a strict JSON generator. Respond only with JSON that "
                        f"matches this schema: {schema_hint}"
                    ),
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        return self._post(payload)

    def why_now(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Provide a short, calm reason (one sentence) for why this "
                        "task should be done now."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
        }
        data = self._post(payload)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip()

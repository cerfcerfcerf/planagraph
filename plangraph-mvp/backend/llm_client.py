from __future__ import annotations

import json
import os
from typing import Any

import httpx

DEFAULT_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEFAULT_MODEL_FAST = os.getenv("OPENAI_MODEL_FAST", "gpt-5-mini")
DEFAULT_MODEL_REASON = os.getenv("OPENAI_MODEL_REASON", "gpt-5.2")


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        model_reason: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or DEFAULT_API_KEY
        self.model = model or DEFAULT_MODEL_FAST
        self.model_reason = model_reason or DEFAULT_MODEL_REASON
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

    def parse_plan(self, text: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a strict JSON generator. Respond only with JSON that "
                        "matches the provided schema."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_schema", "json_schema": schema},
        }
        return self._post(payload)

    def summarize_insights(self, metrics: dict[str, float]) -> dict[str, Any]:
        payload = {
            "model": self.model_reason,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an assistant that writes concise weekly summaries. "
                        "Respond with JSON containing keys: narrative (4-6 sentences) "
                        "and recommendations (list of 3 short items)."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Metrics: {metrics}. Focus on trends and next steps.",
                },
            ],
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        }
        return self._post(payload)

    def lazy_suggestions(self, title: str, notes: str | None = None) -> dict[str, Any]:
        payload = {
            "model": self.model_reason,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You provide concise alternatives for tasks. "
                        "Return JSON with key suggestions as a list of 3 strings."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Task: {title}. Notes: {notes or ''}",
                },
            ],
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        }
        return self._post(payload)

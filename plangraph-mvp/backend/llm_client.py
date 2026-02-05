from __future__ import annotations

import os
import time
from typing import Any

import httpx

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1")
USE_LLM = os.getenv("USE_LLM", "true").lower() == "true"


class LLMClient:
    def __init__(self, base_url: str = LLM_BASE_URL, api_key: str = LLM_API_KEY) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def chat(self, payload: dict[str, Any], retries: int = 2, timeout_s: int = 20) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/chat/completions"
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                with httpx.Client(timeout=timeout_s) as client:
                    response = client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:  # noqa: BLE001 - keep retry logic simple
                last_exc = exc
                if attempt < retries:
                    time.sleep(0.6 * (attempt + 1))
                    continue
                raise exc
        if last_exc:
            raise last_exc
        return {}


client = LLMClient()

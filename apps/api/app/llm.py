import hashlib
import json

import httpx

from app.cache import Cache
from app.config import Settings


class LLMClient:
    """OpenAI-compatible completions with a cache so identical prompts are not sent twice."""

    def __init__(self, settings: Settings, cache: Cache, transport=None):
        self.api_key = settings.vertex_llm_api_key
        self.base_url = settings.vertex_llm_base_url.rstrip("/")
        self.model = settings.vertex_llm_model
        self.cache = cache
        self.transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) or self.transport is not None

    def complete(self, system: str, user: str, *, ttl: int = 3600) -> tuple[str, bool] | None:
        if not self.enabled:
            return None
        key = "llm:" + hashlib.sha256(f"{self.model}\n{system}\n{user}".encode()).hexdigest()
        cached = self.cache.get(key)
        if isinstance(cached, dict) and "text" in cached:
            return cached["text"], True
        text = self._request(system, user)
        self.cache.set(key, {"text": text}, ttl)
        return text, False

    def _request(self, system: str, user: str) -> str:
        if self.transport is not None:
            return self.transport(system, user)
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 1200,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with httpx.Client(timeout=40.0) as client:
            response = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        return body["choices"][0]["message"]["content"]


def parse_json_object(text: str) -> dict | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None

from __future__ import annotations

import json
from typing import Any

from ..config import AISettings
from ..http import HttpJsonClient


class OllamaClient:
    def __init__(self, settings: AISettings, user_agent: str) -> None:
        self.settings = settings
        self.client = HttpJsonClient(
            user_agent=user_agent,
            timeout_seconds=settings.request_timeout_seconds,
            max_retries=1,
        )
        self._availability: bool | None = None

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def is_available(self, refresh: bool = False) -> bool:
        if not self.enabled:
            return False
        if self._availability is not None and not refresh:
            return self._availability
        try:
            payload = self.client.get_json(f"{self.settings.base_url}/api/version")
            self._availability = isinstance(payload, dict) and bool(payload.get("version"))
        except RuntimeError:
            self._availability = False
        return self._availability

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = self.client.post_json(
            f"{self.settings.base_url}/api/embed",
            {
                "model": self.settings.embedding_model,
                "input": texts,
                "truncate": True,
                "keep_alive": "10m",
            },
        )
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RuntimeError("Ollama returned an unexpected embedding response")
        return [[float(value) for value in row] for row in embeddings]

    def chat_text(self, system: str, user: str, temperature: float = 0.2) -> str:
        payload = self.client.post_json(
            f"{self.settings.base_url}/api/chat",
            {
                "model": self.settings.chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": temperature},
                "keep_alive": "10m",
            },
        )
        message = payload.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Ollama returned an unexpected chat response")
        return str(message.get("content") or "").strip()

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        payload = self.client.post_json(
            f"{self.settings.base_url}/api/chat",
            {
                "model": self.settings.chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "format": "json",
                "stream": False,
                "think": False,
                "options": {"temperature": 0.1},
                "keep_alive": "10m",
            },
        )
        message = payload.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Ollama returned an unexpected chat response")
        content = str(message.get("content") or "").strip()
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama did not return valid JSON") from exc
        if not isinstance(value, dict):
            raise RuntimeError("Ollama JSON response was not an object")
        return value

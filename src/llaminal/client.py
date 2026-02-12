"""Async OpenAI-compatible HTTP client for llama.cpp and similar servers."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class Delta:
    """A single streamed delta from the API."""
    content: str | None = None
    tool_calls: list[dict] | None = None
    finish_reason: str | None = None


class LlaminalClient:
    """Wraps httpx.AsyncClient to talk to an OpenAI-compatible chat endpoint."""

    def __init__(self, base_url: str = "http://localhost:8080", model: str = "local-model"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def stream_chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncIterator[Delta]:
        """POST to /v1/chat/completions with stream=True, yield Delta chunks."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        async with self._client.stream(
            "POST", "/v1/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    return

                chunk = json.loads(data)
                choice = chunk["choices"][0]
                delta = choice.get("delta", {})

                yield Delta(
                    content=delta.get("content"),
                    tool_calls=delta.get("tool_calls"),
                    finish_reason=choice.get("finish_reason"),
                )

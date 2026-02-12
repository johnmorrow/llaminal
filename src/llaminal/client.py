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

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        model: str = "local-model",
        api_key: str | None = None,
        temperature: float | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=120.0, headers=headers
        )

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
        if self.temperature is not None:
            payload["temperature"] = self.temperature

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

                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    # Skip malformed chunks from the model
                    continue

                choices = chunk.get("choices")
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta", {})

                yield Delta(
                    content=delta.get("content"),
                    tool_calls=delta.get("tool_calls"),
                    finish_reason=choice.get("finish_reason"),
                )

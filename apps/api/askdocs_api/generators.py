"""Generation adapters: one protocol, three providers, one deterministic fake.

ADR-004: generation is the part worth swapping, so it is the part behind an
interface. The default is local so the whole system is reproducible and free to
demo; hosted adapters exist to show that changing provider is a config change,
not a rewrite.

Cost is computed from the provider's own token counts against a table, never
asserted in prose - that is what makes the README's "cost per query" honest.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import httpx

from askdocs_api.config import get_settings

# USD per 1M tokens (input, output) and an INR conversion. Dated on purpose: a
# price change is a decision, and this table is where it is recorded.
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "ollama": (0.0, 0.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
}
USD_TO_INR = 88.0


@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    provider: str = ""
    model: str = ""

    @property
    def cost_inr(self) -> float:
        rate_in, rate_out = PRICES_USD_PER_MTOK.get(self.model, (0.0, 0.0))
        usd = (self.prompt_tokens / 1e6) * rate_in + (self.completion_tokens / 1e6) * rate_out
        return round(usd * USD_TO_INR, 4)


class Generator(Protocol):
    """Stream tokens; report what it cost."""

    provider: str
    model: str
    usage: Usage

    def stream(self, prompt: str) -> AsyncIterator[str]: ...


class OllamaGenerator:
    """Local default: qwen2.5:7b-instruct through the Ollama HTTP API."""

    provider = "ollama"

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self.usage = Usage(provider=self.provider, model=self.model)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "options": {"temperature": 0.1, "seed": 42, "num_predict": 700},
        }
        timeout = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            request = client.build_request("POST", f"{self.base_url}/api/chat", json=payload)
            response = await client.send(request, stream=True)
            try:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if chunk := event.get("message", {}).get("content"):
                        yield chunk
                    if event.get("done"):
                        self.usage.prompt_tokens = event.get("prompt_eval_count", 0)
                        self.usage.completion_tokens = event.get("eval_count", 0)
                        break
            finally:
                await response.aclose()


class OpenAIGenerator:
    provider = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.usage = Usage(provider=self.provider, model=self.model)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 700,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        timeout = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client, client.stream(
            "POST", "https://api.openai.com/v1/chat/completions", json=payload, headers=headers
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                body = line[6:]
                if body.strip() == "[DONE]":
                    break
                event = json.loads(body)
                if usage := event.get("usage"):
                    self.usage.prompt_tokens = usage.get("prompt_tokens", 0)
                    self.usage.completion_tokens = usage.get("completion_tokens", 0)
                for choice in event.get("choices", []):
                    if delta := choice.get("delta", {}).get("content"):
                        yield delta


class GeminiGenerator:
    provider = "gemini"

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model
        self.usage = Usage(provider=self.provider, model=self.model)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:streamGenerateContent?alt=sse&key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 700},
        }
        timeout = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            request = client.build_request("POST", url, json=payload)
            response = await client.send(request, stream=True)
            try:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    if meta := event.get("usageMetadata"):
                        self.usage.prompt_tokens = meta.get("promptTokenCount", 0)
                        self.usage.completion_tokens = meta.get("candidatesTokenCount", 0)
                    for candidate in event.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            if text := part.get("text"):
                                yield text
            finally:
                await response.aclose()


class EchoGenerator:
    """Deterministic stand-in for tests and for a demo with no model installed.

    It does not answer the question. It streams back the sources it was given with
    their markers, which is enough to exercise SSE ordering, citation validation and
    the refusal path without pretending to be a language model.
    """

    provider = "echo"
    model = "echo-1"

    def __init__(self) -> None:
        self.usage = Usage(provider=self.provider, model=self.model)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        # Count only real source headers ("[1] Income-tax Act…"), never the format
        # example in the prompt's rules — that mistake made the validator reject
        # every echo answer with marker_outside_context, which is the validator
        # doing its job.
        markers = len(re.findall(r"^\[\d{1,2}\] ", prompt, re.MULTILINE))
        text = (
            "Echo mode: no language model is configured, so this answer only repeats the "
            f"sources it was given {''.join(f'[{i}]' for i in range(1, markers + 1))}."
        )
        self.usage.prompt_tokens = len(prompt) // 4
        for word in text.split(" "):
            yield word + " "
        self.usage.completion_tokens = len(text) // 4


def build_generator() -> Generator:
    """Pick the adapter from config; a missing key fails here, not mid-stream."""
    provider = get_settings().generator_provider.lower()
    if provider == "ollama":
        return OllamaGenerator()
    if provider == "openai":
        return OpenAIGenerator()
    if provider == "gemini":
        return GeminiGenerator()
    if provider == "echo":
        return EchoGenerator()
    raise RuntimeError(f"unknown GENERATOR_PROVIDER: {provider}")

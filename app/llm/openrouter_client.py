"""Narrow OpenRouter transport with bounded retries and safe errors."""

import asyncio
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import SecretStr

from app.config import Settings


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMProviderError(RuntimeError):
    status_code = 500


class LLMConfigurationError(LLMProviderError):
    pass


class LLMAuthenticationError(LLMProviderError):
    pass


class LLMRateLimitError(LLMProviderError):
    pass


class LLMQuotaError(LLMProviderError):
    pass


class LLMUnavailableError(LLMProviderError):
    pass


class LLMMalformedResponseError(LLMProviderError):
    pass


class OpenRouterClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._http_client = http_client
        self._next_key_index = 0
        self._key_lock = asyncio.Lock()

    async def complete_structured(
        self,
        messages: list[dict[str, str]],
        schema: Mapping[str, Any],
        model: str | None = None,
    ) -> str:
        api_keys = self.settings.configured_api_keys()
        if not api_keys:
            raise LLMConfigurationError("OpenRouter API key is not configured")
        if self.settings.openrouter_model is None:
            raise LLMConfigurationError("OpenRouter model is not configured")

        selected_model = model or self.settings.openrouter_model
        payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 1200,
            "reasoning": {"effort": "minimal", "exclude": True},
            "stream": False,
            "provider": {"require_parameters": True},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "gridwise_directives",
                    "strict": True,
                    "schema": dict(schema),
                },
            },
        }
        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.openrouter_timeout_seconds)
        )
        try:
            last_rate_limit: LLMRateLimitError | None = None
            for api_key in await self._ordered_keys(api_keys):
                headers = {
                    "Authorization": f"Bearer {api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                    "X-OpenRouter-Title": "GridWise LLM",
                }
                try:
                    response = await self._post_with_retry(client, payload, headers)
                except LLMRateLimitError as exc:
                    last_rate_limit = exc
                    continue
                break
            else:
                raise LLMRateLimitError(
                    "All configured language model keys are rate limited"
                ) from last_rate_limit
        finally:
            if owns_client:
                await client.aclose()

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise TypeError("empty content")
            return content
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMMalformedResponseError("OpenRouter returned a malformed response") from exc

    async def _ordered_keys(self, api_keys: list[SecretStr]) -> list[SecretStr]:
        """Rotate the first key per request while retaining bounded failover order."""

        async with self._key_lock:
            start = self._next_key_index % len(api_keys)
            self._next_key_index = (start + 1) % len(api_keys)
        return api_keys[start:] + api_keys[:start]

    async def _post_with_retry(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = await client.post(OPENROUTER_URL, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt == 0:
                    continue
                raise LLMUnavailableError("Language model request timed out") from exc
            except httpx.HTTPError as exc:
                raise LLMUnavailableError("Language model provider is unavailable") from exc

            if response.status_code in (401, 403):
                raise LLMAuthenticationError("Language model authentication failed")
            if response.status_code == 402:
                raise LLMQuotaError("Language model quota is insufficient")
            if response.status_code == 429:
                raise LLMRateLimitError("Language model rate limit exceeded")
            if response.status_code >= 500:
                if attempt == 0:
                    continue
                raise LLMUnavailableError("Language model provider is unavailable")
            if response.status_code >= 400:
                raise LLMProviderError("Language model request was rejected")
            return response
        raise LLMUnavailableError("Language model provider is unavailable") from last_error

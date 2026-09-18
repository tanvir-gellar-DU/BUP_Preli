"""Narrow OpenRouter transport with bounded retries and safe errors."""

from collections.abc import Mapping
from typing import Any

import httpx

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

    async def complete_structured(
        self, messages: list[dict[str, str]], schema: Mapping[str, Any]
    ) -> str:
        if self.settings.openrouter_api_key is None:
            raise LLMConfigurationError("OpenRouter API key is not configured")
        if self.settings.openrouter_model is None:
            raise LLMConfigurationError("OpenRouter model is not configured")

        payload = {
            "model": self.settings.openrouter_model,
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
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": "GridWise LLM",
        }

        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.openrouter_timeout_seconds)
        )
        try:
            response = await self._post_with_retry(client, payload, headers)
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
                if attempt == 0:
                    continue
                raise LLMRateLimitError("Language model rate limit exceeded")
            if response.status_code >= 500:
                if attempt == 0:
                    continue
                raise LLMUnavailableError("Language model provider is unavailable")
            if response.status_code >= 400:
                raise LLMProviderError("Language model request was rejected")
            return response
        raise LLMUnavailableError("Language model provider is unavailable") from last_error

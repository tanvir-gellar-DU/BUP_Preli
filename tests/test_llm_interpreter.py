import json

import httpx
import pytest

from app.config import Settings
from app.llm.interpreter import DirectiveInterpreter
from app.llm.openrouter_client import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMMalformedResponseError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMUnavailableError,
    OpenRouterClient,
)
from app.llm.prompt import INTERPRETATION_JSON_SCHEMA, build_messages
from app.models.request import OptimizeEnergyRequest


def settings(**overrides) -> Settings:
    values = {
        "openrouter_api_key": "sk-or-test",
        "openrouter_model": "test/model",
        "openrouter_timeout_seconds": 1,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


def no_op_content() -> str:
    return json.dumps(
        {
            "directive_interpretation": [
                {
                    "note_index": 0,
                    "applies": False,
                    "directive_type": "no_op",
                    "structured_adjustment": None,
                    "explanation": "Irrelevant.",
                }
            ]
        }
    )


@pytest.mark.asyncio
async def test_valid_structured_interpretation(copy_request) -> None:
    raw = {
        "directive_interpretation": [
            {
                "note_index": 0,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "Irrelevant.",
            }
        ]
    }
    transport = httpx.MockTransport(lambda request: response(json.dumps(raw)))
    async with httpx.AsyncClient(transport=transport) as http_client:
        interpreter = DirectiveInterpreter(OpenRouterClient(settings(), http_client))
        result = await interpreter.interpret(
            OptimizeEnergyRequest.model_validate(copy_request())
        )
    assert result[0].directive_type.value == "no_op"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "not json",
        json.dumps({"directive_interpretation": []}),
        json.dumps(
            {
                "directive_interpretation": [
                    {
                        "note_index": 0,
                        "applies": True,
                        "directive_type": "unsupported",
                        "structured_adjustment": None,
                        "explanation": "Invalid.",
                    }
                ]
            }
        ),
    ],
)
async def test_rejects_malformed_or_invalid_output(copy_request, content: str) -> None:
    transport = httpx.MockTransport(lambda request: response(content))
    async with httpx.AsyncClient(transport=transport) as http_client:
        interpreter = DirectiveInterpreter(OpenRouterClient(settings(), http_client))
        with pytest.raises(LLMMalformedResponseError):
            await interpreter.interpret(OptimizeEnergyRequest.model_validate(copy_request()))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "primary_content",
    ["", "not json", json.dumps({"directive_interpretation": []})],
)
async def test_malformed_primary_uses_one_fallback_model(
    copy_request, primary_content: str
) -> None:
    models = []

    def handler(request):
        model = json.loads(request.content)["model"]
        models.append(model)
        if model == "test/primary":
            return response(primary_content)
        return response(no_op_content())

    transport = httpx.MockTransport(handler)
    fallback_settings = settings(
        openrouter_model="test/primary",
        openrouter_fallback_model="test/fallback",
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        interpreter = DirectiveInterpreter(
            OpenRouterClient(fallback_settings, http_client)
        )
        result = await interpreter.interpret(
            OptimizeEnergyRequest.model_validate(copy_request())
        )

    assert result[0].directive_type.value == "no_op"
    assert models == ["test/primary", "test/fallback"]


@pytest.mark.asyncio
async def test_model_fallback_is_bounded_to_one_retry(copy_request) -> None:
    models = []

    def handler(request):
        models.append(json.loads(request.content)["model"])
        return response("not json")

    transport = httpx.MockTransport(handler)
    fallback_settings = settings(
        openrouter_model="test/primary",
        openrouter_fallback_model="test/fallback",
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        interpreter = DirectiveInterpreter(
            OpenRouterClient(fallback_settings, http_client)
        )
        with pytest.raises(LLMMalformedResponseError):
            await interpreter.interpret(
                OptimizeEnergyRequest.model_validate(copy_request())
            )

    assert models == ["test/primary", "test/fallback"]


@pytest.mark.asyncio
async def test_provider_failure_does_not_trigger_model_fallback(copy_request) -> None:
    models = []

    def handler(request):
        models.append(json.loads(request.content)["model"])
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    fallback_settings = settings(
        openrouter_model="test/primary",
        openrouter_fallback_model="test/fallback",
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        interpreter = DirectiveInterpreter(
            OpenRouterClient(fallback_settings, http_client)
        )
        with pytest.raises(LLMUnavailableError):
            await interpreter.interpret(
                OptimizeEnergyRequest.model_validate(copy_request())
            )

    assert models == ["test/primary", "test/primary"]


@pytest.mark.asyncio
async def test_missing_key_is_controlled(copy_request) -> None:
    client = OpenRouterClient(settings(openrouter_api_key=None))
    request = OptimizeEnergyRequest.model_validate(copy_request())
    with pytest.raises(LLMConfigurationError, match="key"):
        await client.complete_structured(build_messages(request), INTERPRETATION_JSON_SCHEMA)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error_type"),
    [(401, LLMAuthenticationError), (402, LLMQuotaError), (429, LLMRateLimitError), (503, LLMUnavailableError)],
)
async def test_provider_status_mapping(copy_request, status: int, error_type: type[Exception]) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status))
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OpenRouterClient(settings(), http_client)
        request = OptimizeEnergyRequest.model_validate(copy_request())
        with pytest.raises(error_type):
            await client.complete_structured(
                build_messages(request), INTERPRETATION_JSON_SCHEMA
            )


@pytest.mark.asyncio
async def test_rate_limit_immediately_fails_over_to_next_key(copy_request) -> None:
    authorizations = []

    def handler(request):
        authorization = request.headers["authorization"]
        authorizations.append(authorization)
        if authorization == "Bearer sk-or-first":
            return httpx.Response(429)
        return response(no_op_content())

    transport = httpx.MockTransport(handler)
    pool_settings = settings(
        openrouter_api_key=None,
        openrouter_api_keys=["sk-or-first", "sk-or-second"],
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OpenRouterClient(pool_settings, http_client)
        request = OptimizeEnergyRequest.model_validate(copy_request())
        content = await client.complete_structured(
            build_messages(request), INTERPRETATION_JSON_SCHEMA
        )

    assert json.loads(content)["directive_interpretation"][0]["directive_type"] == "no_op"
    assert authorizations == ["Bearer sk-or-first", "Bearer sk-or-second"]


@pytest.mark.asyncio
async def test_rate_limit_stops_after_every_key_once(copy_request) -> None:
    authorizations = []

    def handler(request):
        authorizations.append(request.headers["authorization"])
        return httpx.Response(429)

    transport = httpx.MockTransport(handler)
    pool_settings = settings(
        openrouter_api_key=None,
        openrouter_api_keys=["sk-or-first", "sk-or-second"],
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OpenRouterClient(pool_settings, http_client)
        request = OptimizeEnergyRequest.model_validate(copy_request())
        with pytest.raises(LLMRateLimitError, match="All configured"):
            await client.complete_structured(
                build_messages(request), INTERPRETATION_JSON_SCHEMA
            )

    assert authorizations == ["Bearer sk-or-first", "Bearer sk-or-second"]


@pytest.mark.asyncio
async def test_key_pool_rotates_starting_key_between_requests(copy_request) -> None:
    authorizations = []

    def handler(request):
        authorizations.append(request.headers["authorization"])
        return response(no_op_content())

    transport = httpx.MockTransport(handler)
    pool_settings = settings(
        openrouter_api_key=None,
        openrouter_api_keys=["sk-or-first", "sk-or-second"],
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OpenRouterClient(pool_settings, http_client)
        request = OptimizeEnergyRequest.model_validate(copy_request())
        for _ in range(2):
            await client.complete_structured(
                build_messages(request), INTERPRETATION_JSON_SCHEMA
            )

    assert authorizations == ["Bearer sk-or-first", "Bearer sk-or-second"]


def test_key_pool_deduplicates_legacy_key() -> None:
    configured = settings(
        openrouter_api_key="sk-or-first",
        openrouter_api_keys=["sk-or-first", "sk-or-second"],
    ).configured_api_keys()

    assert [key.get_secret_value() for key in configured] == [
        "sk-or-first",
        "sk-or-second",
    ]


@pytest.mark.asyncio
async def test_timeout_is_retried_then_controlled(copy_request) -> None:
    calls = 0

    def timeout(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow", request=request)

    transport = httpx.MockTransport(timeout)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OpenRouterClient(settings(), http_client)
        request = OptimizeEnergyRequest.model_validate(copy_request())
        with pytest.raises(LLMUnavailableError, match="timed out"):
            await client.complete_structured(
                build_messages(request), INTERPRETATION_JSON_SCHEMA
            )
    assert calls == 2


def test_prompt_contains_context_and_schema_is_strict(copy_request) -> None:
    request = OptimizeEnergyRequest.model_validate(copy_request())
    messages = build_messages(request)
    assert '"battery_capacity_kwh":20.0' in messages[1]["content"]
    assert INTERPRETATION_JSON_SCHEMA["additionalProperties"] is False


@pytest.mark.asyncio
async def test_provider_payload_uses_minimal_excluded_reasoning(copy_request) -> None:
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return response(
            json.dumps(
                {
                    "directive_interpretation": [
                        {
                            "note_index": 0,
                            "applies": False,
                            "directive_type": "no_op",
                            "structured_adjustment": None,
                            "explanation": "Irrelevant.",
                        }
                    ]
                }
            )
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OpenRouterClient(settings(), http_client)
        request = OptimizeEnergyRequest.model_validate(copy_request())
        await client.complete_structured(build_messages(request), INTERPRETATION_JSON_SCHEMA)

    assert captured["reasoning"] == {"effort": "minimal", "exclude": True}
    assert captured["provider"] == {"require_parameters": True}

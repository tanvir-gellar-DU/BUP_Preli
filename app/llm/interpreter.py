"""Structured parsing and guardrailing of language-model output."""

import json

from pydantic import ValidationError

from app.guardrails.directive_validator import DirectiveValidationError, validate_directives
from app.llm.openrouter_client import LLMMalformedResponseError, OpenRouterClient
from app.llm.prompt import INTERPRETATION_JSON_SCHEMA, build_messages
from app.models.directives import DirectiveInterpretation, InterpretationBatch
from app.models.request import OptimizeEnergyRequest


class DirectiveInterpreter:
    def __init__(self, client: OpenRouterClient) -> None:
        self.client = client

    async def interpret(self, request: OptimizeEnergyRequest) -> list[DirectiveInterpretation]:
        content = await self.client.complete_structured(
            build_messages(request), INTERPRETATION_JSON_SCHEMA
        )
        try:
            raw = json.loads(content)
            batch = InterpretationBatch.model_validate(raw)
            return validate_directives(batch.directive_interpretation, request)
        except (json.JSONDecodeError, ValidationError, DirectiveValidationError) as exc:
            raise LLMMalformedResponseError(
                "Language model returned an invalid directive interpretation"
            ) from exc

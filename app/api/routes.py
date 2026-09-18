"""GridWise HTTP routes."""

from typing import Literal, TypedDict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import get_settings
from app.llm.interpreter import DirectiveInterpreter
from app.llm.openrouter_client import LLMProviderError, OpenRouterClient
from app.models.request import OptimizeEnergyRequest
from app.models.response import OptimizeEnergyResponse
from app.optimization.optimizer import OptimizationError
from app.services.optimization_service import OptimizationService
from app.validation.schedule_validator import ScheduleValidationError


class HealthResponse(TypedDict):
    status: Literal["ok"]


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report readiness without depending on OpenRouter or the optimizer."""

    return {"status": "ok"}


def get_optimization_service(request: Request) -> OptimizationService:
    http_client: httpx.AsyncClient | None = getattr(request.app.state, "http_client", None)
    provider = OpenRouterClient(get_settings(), http_client=http_client)
    return OptimizationService(DirectiveInterpreter(provider))


@router.post(
    "/optimize-energy",
    response_model=OptimizeEnergyResponse,
    responses={
        400: {"description": "Malformed JSON or structurally invalid request"},
        422: {"description": "Well-formed scenario with no feasible schedule"},
        500: {"description": "Controlled provider or internal validation failure"},
    },
)
async def optimize_energy(
    payload: OptimizeEnergyRequest,
    service: OptimizationService = Depends(get_optimization_service),
) -> OptimizeEnergyResponse:
    try:
        return await service.optimize(payload)
    except LLMProviderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None
    except OptimizationError as exc:
        raise HTTPException(status_code=422, detail="Scenario has no feasible schedule") from exc
    except ScheduleValidationError as exc:
        raise HTTPException(status_code=500, detail="Candidate schedule failed validation") from exc

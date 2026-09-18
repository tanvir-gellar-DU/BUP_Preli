import json
from pathlib import Path

import pytest

from app.models.directives import DirectiveInterpretation
from app.models.request import OptimizeEnergyRequest
from app.services.optimization_service import OptimizationService


SAMPLE_PATH = Path(__file__).parents[1] / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
CASES = json.loads(SAMPLE_PATH.read_text())["cases"]


class ReferenceInterpreter:
    def __init__(self, raw_interpretations: list[dict]) -> None:
        self.interpretations = [
            DirectiveInterpretation.model_validate(item) for item in raw_interpretations
        ]

    async def interpret(self, request):
        return self.interpretations


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_public_case_optimization_matches_reference_cost(case: dict) -> None:
    request = OptimizeEnergyRequest.model_validate(case["input"])
    expected = case["expected_output"]
    service = OptimizationService(ReferenceInterpreter(expected["directive_interpretation"]))
    result = await service.optimize(request)
    assert result.scenario_id == case["id"]
    assert result.total_cost_bdt == pytest.approx(expected["total_cost_bdt"], abs=0.01)
    assert result.total_grid_kwh == pytest.approx(expected["total_grid_kwh"], abs=0.01)
    assert result.peak_grid_kwh >= 0
    assert result.hourly_plan[-1].battery_energy_after_kwh == pytest.approx(
        request.battery.initial_energy_kwh, abs=0.01
    )

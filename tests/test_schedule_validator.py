from copy import deepcopy

import pytest

from app.models.directives import DirectiveInterpretation
from app.models.request import OptimizeEnergyRequest
from app.models.response import HourlyPlanEntry
from app.optimization.directive_application import apply_directives
from app.optimization.optimizer import optimize_schedule
from app.optimization.result_mapper import map_optimizer_result
from app.validation.schedule_validator import ScheduleValidationError, validate_schedule


def valid_setup(copy_request):
    request = OptimizeEnergyRequest.model_validate(copy_request())
    noop = DirectiveInterpretation.model_validate({"note_index": 0, "applies": False,
        "directive_type": "no_op", "structured_adjustment": None, "explanation": "none"})
    constraints = apply_directives(request, [noop])
    plan = map_optimizer_result(optimize_schedule(request, constraints))
    return request, constraints, plan


@pytest.mark.parametrize("mutation", ["grid", "solar", "state", "capacity", "rate", "final"])
def test_mutations_are_rejected(copy_request, mutation: str) -> None:
    request, constraints, plan = valid_setup(copy_request)
    raw = [x.model_dump() for x in plan]
    if mutation == "grid": raw[5]["grid_kwh"] += 1
    elif mutation == "solar": raw[0]["solar_used_kwh"] = 1
    elif mutation == "state": raw[5]["battery_energy_after_kwh"] += 1
    elif mutation == "capacity": raw[0].update(battery_action="charge", battery_kwh=11, battery_energy_after_kwh=21, grid_kwh=21)
    elif mutation == "rate": raw[0].update(battery_action="charge", battery_kwh=6, battery_energy_after_kwh=16, grid_kwh=16)
    elif mutation == "final": raw[23]["battery_energy_after_kwh"] += 1
    corrupted = [HourlyPlanEntry.model_validate(x) for x in raw]
    with pytest.raises(ScheduleValidationError):
        validate_schedule(request, constraints, corrupted)

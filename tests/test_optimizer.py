import pytest

from app.models.directives import DirectiveInterpretation
from app.models.request import OptimizeEnergyRequest
from app.optimization.directive_application import apply_directives
from app.optimization.optimizer import OptimizationError, optimize_schedule
from app.optimization.result_mapper import map_optimizer_result
from app.validation.schedule_validator import validate_schedule


def no_op() -> DirectiveInterpretation:
    return DirectiveInterpretation.model_validate({
        "note_index": 0, "applies": False, "directive_type": "no_op",
        "structured_adjustment": None, "explanation": "none",
    })


def test_optimizer_shifts_energy_and_returns_to_initial(copy_request) -> None:
    data = copy_request()
    for h in data["hours"]:
        h["solar_kwh"] = 0
        h["tariff_bdt_per_kwh"] = 1 if h["hour"] < 12 else 10
    request = OptimizeEnergyRequest.model_validate(data)
    constraints = apply_directives(request, [no_op()])
    plan = map_optimizer_result(optimize_schedule(request, constraints))
    aggregates = validate_schedule(request, constraints, plan)
    assert plan[-1].battery_energy_after_kwh == pytest.approx(request.battery.initial_energy_kwh)
    assert any(x.battery_action == "charge" for x in plan[:12])
    assert any(x.battery_action == "discharge" for x in plan[12:])
    assert aggregates.total_cost_bdt < 24 * 10 * 10


def test_optimizer_honors_no_charge_and_grid_cap(copy_request) -> None:
    data = copy_request()
    data["operator_notes"] = ["no charge", "cap"]
    request = OptimizeEnergyRequest.model_validate(data)
    directives = [
        DirectiveInterpretation.model_validate({"note_index": 0, "applies": True,
            "directive_type": "no_charge_window", "structured_adjustment": {"hours": [2, 3]}, "explanation": "x"}),
        DirectiveInterpretation.model_validate({"note_index": 1, "applies": True,
            "directive_type": "max_grid_window", "structured_adjustment": {"hours": [18], "max_grid_kwh": 8}, "explanation": "x"}),
    ]
    constraints = apply_directives(request, directives)
    plan = map_optimizer_result(optimize_schedule(request, constraints))
    validate_schedule(request, constraints, plan)
    assert plan[2].battery_action != "charge"
    assert plan[3].battery_action != "charge"
    assert plan[18].grid_kwh <= 8 + 1e-5


def test_infeasible_scenario_is_controlled(copy_request) -> None:
    data = copy_request()
    data["operator_notes"] = ["cap"]
    request = OptimizeEnergyRequest.model_validate(data)
    cap = DirectiveInterpretation.model_validate({"note_index": 0, "applies": True,
        "directive_type": "max_grid_window", "structured_adjustment": {"hours": list(range(24)), "max_grid_kwh": 0}, "explanation": "x"})
    constraints = apply_directives(request, [cap])
    with pytest.raises(OptimizationError):
        optimize_schedule(request, constraints)

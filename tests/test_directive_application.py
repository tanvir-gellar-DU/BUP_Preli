from app.models.directives import DirectiveInterpretation
from app.models.request import OptimizeEnergyRequest
from app.optimization.directive_application import apply_directives


def directive(index: int, kind: str, adjustment: dict) -> DirectiveInterpretation:
    return DirectiveInterpretation.model_validate(
        {"note_index": index, "applies": True, "directive_type": kind,
         "structured_adjustment": adjustment, "explanation": "test"}
    )


def test_applies_all_directive_constraints(copy_request) -> None:
    data = copy_request()
    data["operator_notes"] = ["one", "two", "three"]
    request = OptimizeEnergyRequest.model_validate(data)
    applied = apply_directives(request, [
        directive(0, "solar_reduction", {"hours": [10], "factor": 0.25}),
        directive(1, "minimum_battery_reserve", {"hours": [18], "minimum_energy_kwh": 12}),
        directive(2, "max_grid_window", {"hours": [19], "max_grid_kwh": 8}),
        directive(3, "no_charge_window", {"hours": [2]}),
        directive(4, "no_discharge_window", {"hours": [3]}),
    ])
    assert applied.effective_solar[10] == 0.5
    assert applied.minimum_reserve[18] == 12
    assert applied.max_grid[19] == 8
    assert not applied.charge_allowed[2]
    assert not applied.discharge_allowed[3]


def test_overlaps_use_most_restrictive_value(copy_request) -> None:
    request = OptimizeEnergyRequest.model_validate(copy_request())
    applied = apply_directives(request, [
        directive(0, "solar_reduction", {"hours": [10], "factor": 0.8}),
        directive(1, "solar_reduction", {"hours": [10], "factor": 0.4}),
    ])
    assert applied.effective_solar[10] == 0.8

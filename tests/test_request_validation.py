import math

import pytest
from pydantic import ValidationError

from app.models.request import OptimizeEnergyRequest


def test_valid_request_and_unsorted_hours_are_accepted(copy_request) -> None:
    data = copy_request()
    data["hours"].reverse()
    request = OptimizeEnergyRequest.model_validate(data)
    assert [entry.hour for entry in request.hours_by_number()] == list(range(24))


@pytest.mark.parametrize("count", [23, 25])
def test_requires_exactly_24_hours(copy_request, count: int) -> None:
    data = copy_request()
    if count == 23:
        data["hours"] = data["hours"][:23]
    else:
        data["hours"].append({**data["hours"][-1], "hour": 23})
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(data)


def test_rejects_duplicate_or_missing_hour(copy_request) -> None:
    data = copy_request()
    data["hours"][23]["hour"] = 22
    with pytest.raises(ValidationError, match="uniquely cover"):
        OptimizeEnergyRequest.model_validate(data)


@pytest.mark.parametrize("hour", [-1, 24, 1.5, True])
def test_rejects_invalid_hour(copy_request, hour) -> None:
    data = copy_request()
    data["hours"][0]["hour"] = hour
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(data)


@pytest.mark.parametrize("notes", [[], ["a", "b", "c", "d"], [" "]])
def test_rejects_invalid_notes(copy_request, notes: list[str]) -> None:
    data = copy_request()
    data["operator_notes"] = notes
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(data)


@pytest.mark.parametrize("value", [-1, math.inf, -math.inf, math.nan])
def test_rejects_invalid_hour_numbers(copy_request, value: float) -> None:
    data = copy_request()
    data["hours"][0]["demand_kwh"] = value
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [("minimum_energy_kwh", 11), ("initial_energy_kwh", 21), ("capacity_kwh", math.inf)],
)
def test_rejects_invalid_battery_configuration(copy_request, field: str, value: float) -> None:
    data = copy_request()
    data["battery"][field] = value
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(data)


def test_rejects_unknown_fields(copy_request) -> None:
    data = copy_request()
    data["unexpected"] = True
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(data)

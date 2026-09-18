"""Independent replay of a candidate plan without using solver state."""

from dataclasses import dataclass

from app.models.request import OptimizeEnergyRequest
from app.models.response import HourlyPlanEntry
from app.optimization.directive_application import AppliedDirectives


TOLERANCE = 1e-5


class ScheduleValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Aggregates:
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float


def validate_schedule(
    request: OptimizeEnergyRequest,
    constraints: AppliedDirectives,
    plan: list[HourlyPlanEntry],
) -> Aggregates:
    if len(plan) != 24 or [entry.hour for entry in plan] != list(range(24)):
        raise ScheduleValidationError("hourly_plan must contain ordered hours 0 through 23")

    hours = request.hours_by_number()
    before = request.battery.initial_energy_kwh
    for h, item in enumerate(plan):
        if item.solar_used_kwh > constraints.effective_solar[h] + TOLERANCE:
            raise ScheduleValidationError(f"hour {h}: solar usage exceeds effective solar")
        if item.battery_action == "charge":
            if not constraints.charge_allowed[h]:
                raise ScheduleValidationError(f"hour {h}: charging is prohibited")
            if item.battery_kwh > request.battery.max_charge_kwh_per_hour + TOLERANCE:
                raise ScheduleValidationError(f"hour {h}: charge rate exceeded")
            charge, discharge = item.battery_kwh, 0.0
        elif item.battery_action == "discharge":
            if not constraints.discharge_allowed[h]:
                raise ScheduleValidationError(f"hour {h}: discharging is prohibited")
            if item.battery_kwh > request.battery.max_discharge_kwh_per_hour + TOLERANCE:
                raise ScheduleValidationError(f"hour {h}: discharge rate exceeded")
            charge, discharge = 0.0, item.battery_kwh
        else:
            if item.battery_kwh > TOLERANCE:
                raise ScheduleValidationError(f"hour {h}: idle action has nonzero magnitude")
            charge = discharge = 0.0

        expected_after = before + charge - discharge
        if abs(item.battery_energy_after_kwh - expected_after) > TOLERANCE:
            raise ScheduleValidationError(f"hour {h}: invalid battery transition")
        if item.battery_energy_after_kwh < constraints.minimum_reserve[h] - TOLERANCE:
            raise ScheduleValidationError(f"hour {h}: reserve violated")
        if item.battery_energy_after_kwh > request.battery.capacity_kwh + TOLERANCE:
            raise ScheduleValidationError(f"hour {h}: capacity exceeded")
        cap = constraints.max_grid[h]
        if cap is not None and item.grid_kwh > cap + TOLERANCE:
            raise ScheduleValidationError(f"hour {h}: grid cap exceeded")
        balance = item.grid_kwh + item.solar_used_kwh + discharge
        required = hours[h].demand_kwh + charge
        if abs(balance - required) > TOLERANCE:
            raise ScheduleValidationError(f"hour {h}: energy balance violated")
        before = item.battery_energy_after_kwh

    if abs(before - request.battery.initial_energy_kwh) > TOLERANCE:
        raise ScheduleValidationError("end-of-day battery neutrality violated")

    total_grid = sum(item.grid_kwh for item in plan)
    total_cost = sum(plan[h].grid_kwh * hours[h].tariff_bdt_per_kwh for h in range(24))
    return Aggregates(total_grid, total_cost, max(item.grid_kwh for item in plan))

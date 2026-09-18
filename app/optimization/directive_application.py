"""Convert validated directives into solver-independent hourly constraints."""

from dataclasses import dataclass

from app.models.directives import (
    DirectiveInterpretation,
    DirectiveType,
    MaxGridWindowAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeWindowAdjustment,
    NoDischargeWindowAdjustment,
    SolarReductionAdjustment,
)
from app.models.request import OptimizeEnergyRequest


@dataclass(frozen=True)
class AppliedDirectives:
    effective_solar: tuple[float, ...]
    minimum_reserve: tuple[float, ...]
    charge_allowed: tuple[bool, ...]
    discharge_allowed: tuple[bool, ...]
    max_grid: tuple[float | None, ...]


def apply_directives(
    request: OptimizeEnergyRequest,
    interpretations: list[DirectiveInterpretation],
) -> AppliedDirectives:
    hours = request.hours_by_number()
    effective_solar = [entry.solar_kwh for entry in hours]
    minimum_reserve = [request.battery.minimum_energy_kwh] * 24
    charge_allowed = [True] * 24
    discharge_allowed = [True] * 24
    max_grid: list[float | None] = [None] * 24

    for item in interpretations:
        adjustment = item.structured_adjustment
        if item.directive_type is DirectiveType.NO_OP:
            continue
        if isinstance(adjustment, SolarReductionAdjustment):
            for hour in adjustment.hours:
                candidate = hours[hour].solar_kwh * adjustment.factor
                effective_solar[hour] = min(effective_solar[hour], candidate)
        elif isinstance(adjustment, MinimumBatteryReserveAdjustment):
            for hour in adjustment.hours:
                minimum_reserve[hour] = max(
                    minimum_reserve[hour], adjustment.minimum_energy_kwh
                )
        elif isinstance(adjustment, NoChargeWindowAdjustment):
            for hour in adjustment.hours:
                charge_allowed[hour] = False
        elif isinstance(adjustment, NoDischargeWindowAdjustment):
            for hour in adjustment.hours:
                discharge_allowed[hour] = False
        elif isinstance(adjustment, MaxGridWindowAdjustment):
            for hour in adjustment.hours:
                current = max_grid[hour]
                max_grid[hour] = (
                    adjustment.max_grid_kwh
                    if current is None
                    else min(current, adjustment.max_grid_kwh)
                )

    return AppliedDirectives(
        effective_solar=tuple(effective_solar),
        minimum_reserve=tuple(minimum_reserve),
        charge_allowed=tuple(charge_allowed),
        discharge_allowed=tuple(discharge_allowed),
        max_grid=tuple(max_grid),
    )

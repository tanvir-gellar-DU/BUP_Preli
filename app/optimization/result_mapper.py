"""Map internal signed battery flow to the organizer response action schema."""

from app.models.response import HourlyPlanEntry
from app.optimization.optimizer import OptimizerHour


ACTION_TOLERANCE = 1e-7


def map_optimizer_result(result: list[OptimizerHour]) -> list[HourlyPlanEntry]:
    plan = []
    for item in result:
        if item.battery_flow_kwh > ACTION_TOLERANCE:
            action, magnitude = "charge", item.battery_flow_kwh
        elif item.battery_flow_kwh < -ACTION_TOLERANCE:
            action, magnitude = "discharge", -item.battery_flow_kwh
        else:
            action, magnitude = "idle", 0.0
        plan.append(
            HourlyPlanEntry(
                hour=item.hour,
                grid_kwh=max(0.0, item.grid_kwh),
                solar_used_kwh=max(0.0, item.solar_used_kwh),
                battery_action=action,
                battery_kwh=magnitude,
                battery_energy_after_kwh=max(0.0, item.battery_energy_after_kwh),
            )
        )
    return plan

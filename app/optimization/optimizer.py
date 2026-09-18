"""Cost-minimizing 24-hour linear program."""

from dataclasses import dataclass

import pulp

from app.models.request import OptimizeEnergyRequest
from app.optimization.directive_application import AppliedDirectives


class OptimizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class OptimizerHour:
    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_flow_kwh: float
    battery_energy_after_kwh: float


def optimize_schedule(
    request: OptimizeEnergyRequest, constraints: AppliedDirectives
) -> list[OptimizerHour]:
    hours = request.hours_by_number()
    battery = request.battery
    problem = pulp.LpProblem("gridwise_energy", pulp.LpMinimize)

    grid = [pulp.LpVariable(f"grid_{h}", lowBound=0) for h in range(24)]
    solar = [
        pulp.LpVariable(f"solar_{h}", lowBound=0, upBound=constraints.effective_solar[h])
        for h in range(24)
    ]
    flow = []
    energy = []
    for h in range(24):
        lower = -battery.max_discharge_kwh_per_hour if constraints.discharge_allowed[h] else 0
        upper = battery.max_charge_kwh_per_hour if constraints.charge_allowed[h] else 0
        flow.append(pulp.LpVariable(f"battery_flow_{h}", lowBound=lower, upBound=upper))
        energy.append(
            pulp.LpVariable(
                f"battery_energy_{h}",
                lowBound=constraints.minimum_reserve[h],
                upBound=battery.capacity_kwh,
            )
        )

        problem += grid[h] + solar[h] == hours[h].demand_kwh + flow[h]
        previous = battery.initial_energy_kwh if h == 0 else energy[h - 1]
        problem += energy[h] == previous + flow[h]
        if constraints.max_grid[h] is not None:
            problem += grid[h] <= constraints.max_grid[h]

    problem += energy[23] == battery.initial_energy_kwh
    problem += pulp.lpSum(grid[h] * hours[h].tariff_bdt_per_kwh for h in range(24))

    status = problem.solve(pulp.PULP_CBC_CMD(msg=False, threads=1))
    if pulp.LpStatus[status] != "Optimal":
        raise OptimizationError(f"optimization did not produce an optimal plan: {pulp.LpStatus[status]}")

    def value(variable: pulp.LpVariable) -> float:
        result = variable.value()
        if result is None:
            raise OptimizationError("solver omitted a required variable value")
        return 0.0 if abs(result) < 1e-8 else float(result)

    return [
        OptimizerHour(
            hour=h,
            grid_kwh=value(grid[h]),
            solar_used_kwh=value(solar[h]),
            battery_flow_kwh=value(flow[h]),
            battery_energy_after_kwh=value(energy[h]),
        )
        for h in range(24)
    ]

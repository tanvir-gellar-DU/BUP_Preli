"""End-to-end optimization orchestration."""

from app.llm.interpreter import DirectiveInterpreter
from app.models.directives import DirectiveInterpretation, DirectiveType
from app.models.request import OptimizeEnergyRequest
from app.models.response import OptimizeEnergyResponse
from app.optimization.directive_application import apply_directives
from app.optimization.optimizer import optimize_schedule
from app.optimization.result_mapper import map_optimizer_result
from app.validation.schedule_validator import validate_schedule


class OptimizationService:
    def __init__(self, interpreter: DirectiveInterpreter) -> None:
        self.interpreter = interpreter

    async def optimize(self, request: OptimizeEnergyRequest) -> OptimizeEnergyResponse:
        interpretations = await self.interpreter.interpret(request)
        constraints = apply_directives(request, interpretations)
        candidate = optimize_schedule(request, constraints)
        plan = map_optimizer_result(candidate)
        aggregates = validate_schedule(request, constraints, plan)
        return OptimizeEnergyResponse(
            scenario_id=request.scenario_id,
            directive_interpretation=interpretations,
            hourly_plan=plan,
            total_grid_kwh=aggregates.total_grid_kwh,
            total_cost_bdt=aggregates.total_cost_bdt,
            peak_grid_kwh=aggregates.peak_grid_kwh,
            plan_summary=_build_summary(interpretations),
        )


def _build_summary(interpretations: list[DirectiveInterpretation]) -> str:
    active = [
        item.directive_type.value
        for item in interpretations
        if item.directive_type is not DirectiveType.NO_OP
    ]
    ignored = sum(item.directive_type is DirectiveType.NO_OP for item in interpretations)
    if active:
        text = "Applied " + ", ".join(active) + " and produced a minimum-cost valid schedule"
    else:
        text = "No schedule-changing directives applied; produced a minimum-cost valid schedule"
    if ignored:
        text += f" while ignoring {ignored} irrelevant note{'s' if ignored != 1 else ''}"
    return text + " with the final battery restored to its initial energy."

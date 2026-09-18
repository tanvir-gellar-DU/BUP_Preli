"""Scenario-aware deterministic validation for model interpretations."""

from app.models.directives import (
    DirectiveInterpretation,
    DirectiveType,
    MinimumBatteryReserveAdjustment,
)
from app.models.request import OptimizeEnergyRequest


class DirectiveValidationError(ValueError):
    """Raised when otherwise typed model output is semantically unsafe."""


def validate_directives(
    interpretations: list[DirectiveInterpretation],
    request: OptimizeEnergyRequest,
) -> list[DirectiveInterpretation]:
    expected_indices = list(range(len(request.operator_notes)))
    actual_indices = [item.note_index for item in interpretations]
    if actual_indices != expected_indices:
        raise DirectiveValidationError(
            "interpretations must map exactly once to every note in note_index order"
        )

    for item in interpretations:
        if item.directive_type is DirectiveType.MINIMUM_BATTERY_RESERVE:
            adjustment = item.structured_adjustment
            assert isinstance(adjustment, MinimumBatteryReserveAdjustment)
            if adjustment.minimum_energy_kwh > request.battery.capacity_kwh:
                raise DirectiveValidationError(
                    "minimum battery reserve cannot exceed battery capacity"
                )
    return interpretations

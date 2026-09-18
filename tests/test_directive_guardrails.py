import pytest

from app.guardrails.directive_validator import DirectiveValidationError, validate_directives
from app.models.directives import DirectiveInterpretation
from app.models.request import OptimizeEnergyRequest


def make_no_op(index: int) -> DirectiveInterpretation:
    return DirectiveInterpretation.model_validate(
        {
            "note_index": index,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "Irrelevant.",
        }
    )


def test_requires_exact_note_order(copy_request) -> None:
    data = copy_request()
    data["operator_notes"] = ["one", "two"]
    request = OptimizeEnergyRequest.model_validate(data)
    with pytest.raises(DirectiveValidationError, match="note_index order"):
        validate_directives([make_no_op(1), make_no_op(0)], request)


def test_rejects_reserve_above_capacity(copy_request) -> None:
    request = OptimizeEnergyRequest.model_validate(copy_request())
    reserve = DirectiveInterpretation.model_validate(
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "minimum_battery_reserve",
            "structured_adjustment": {"hours": [18], "minimum_energy_kwh": 21},
            "explanation": "Reserve.",
        }
    )
    with pytest.raises(DirectiveValidationError, match="capacity"):
        validate_directives([reserve], request)


def test_accepts_complete_mapping(copy_request) -> None:
    request = OptimizeEnergyRequest.model_validate(copy_request())
    values = [make_no_op(0)]
    assert validate_directives(values, request) == values

import math

import pytest
from pydantic import ValidationError

from app.models.directives import DirectiveInterpretation


@pytest.mark.parametrize(
    ("directive_type", "adjustment"),
    [
        ("solar_reduction", {"hours": [13, 14], "factor": 0.2}),
        ("minimum_battery_reserve", {"hours": [18, 19], "minimum_energy_kwh": 12}),
        ("no_charge_window", {"hours": [10, 11]}),
        ("no_discharge_window", {"hours": [17, 18]}),
        ("max_grid_window", {"hours": [19, 20], "max_grid_kwh": 15}),
    ],
)
def test_all_real_directives(directive_type: str, adjustment: dict) -> None:
    item = DirectiveInterpretation.model_validate(
        {
            "note_index": 0,
            "applies": True,
            "directive_type": directive_type,
            "structured_adjustment": adjustment,
            "explanation": "Valid interpretation.",
        }
    )
    assert item.directive_type.value == directive_type


def test_no_op() -> None:
    item = DirectiveInterpretation.model_validate(
        {
            "note_index": 0,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "Irrelevant.",
        }
    )
    assert item.structured_adjustment is None


@pytest.mark.parametrize(
    "patch",
    [
        {"directive_type": "unsupported"},
        {"applies": False},
        {"structured_adjustment": None},
        {"structured_adjustment": {"hours": [13, 13], "factor": 0.2}},
        {"structured_adjustment": {"hours": [14, 13], "factor": 0.2}},
        {"structured_adjustment": {"hours": [-1], "factor": 0.2}},
        {"structured_adjustment": {"hours": [24], "factor": 0.2}},
        {"structured_adjustment": {"hours": [13]}},
        {"structured_adjustment": {"hours": [13], "factor": math.nan}},
        {"structured_adjustment": {"hours": [13], "factor": 1.1}},
        {"structured_adjustment": {"hours": [13], "factor": 0.2, "max_grid_kwh": 3}},
    ],
)
def test_rejects_invalid_real_directive(patch: dict) -> None:
    data = {
        "note_index": 0,
        "applies": True,
        "directive_type": "solar_reduction",
        "structured_adjustment": {"hours": [13, 14], "factor": 0.2},
        "explanation": "Solar reduced.",
    }
    data.update(patch)
    with pytest.raises(ValidationError):
        DirectiveInterpretation.model_validate(data)


@pytest.mark.parametrize(
    "patch",
    [
        {"applies": True},
        {"structured_adjustment": {"hours": [1]}},
    ],
)
def test_rejects_invalid_no_op(patch: dict) -> None:
    data = {
        "note_index": 0,
        "applies": False,
        "directive_type": "no_op",
        "structured_adjustment": None,
        "explanation": "Irrelevant.",
    }
    data.update(patch)
    with pytest.raises(ValidationError):
        DirectiveInterpretation.model_validate(data)

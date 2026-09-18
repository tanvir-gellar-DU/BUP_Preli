"""Prompt and provider JSON Schema for semantic directive extraction only."""

import json

from app.models.request import OptimizeEnergyRequest


SYSTEM_PROMPT = """You extract exactly one GridWise directive for every operator note.
Return only data matching the supplied JSON Schema, preserving note_index order.

Allowed directives:
- solar_reduction: hours and factor (usable fraction remaining, 0..1). An 80% reduction means factor 0.2.
- minimum_battery_reserve: hours and absolute minimum_energy_kwh. Convert capacity percentages using the supplied battery capacity.
- no_charge_window: hours.
- no_discharge_window: hours.
- max_grid_window: hours and max_grid_kwh.
- no_op: applies false and null adjustment for notes irrelevant to this 24-hour energy schedule.

Every real directive has applies true. Hours are unique ascending integers 0..23. Time windows are start-inclusive and end-exclusive: 1 PM to 3 PM is [13,14]. Never invent missing values, unsupported directives, demand, tariff, solar, or battery parameters. Do not optimize or propose a schedule."""


def _adjustment_schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "hours": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 23},
                "minItems": 1,
                "maxItems": 24,
            },
            **properties,
        },
        "required": ["hours", *required],
        "additionalProperties": False,
    }


def _directive_schema(name: str, adjustment: dict | None, applies: bool) -> dict:
    return {
        "type": "object",
        "properties": {
            "note_index": {"type": "integer", "minimum": 0},
            "applies": {"const": applies},
            "directive_type": {"const": name},
            "structured_adjustment": adjustment if adjustment is not None else {"type": "null"},
            "explanation": {"type": "string", "minLength": 1},
        },
        "required": [
            "note_index",
            "applies",
            "directive_type",
            "structured_adjustment",
            "explanation",
        ],
        "additionalProperties": False,
    }


INTERPRETATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "directive_interpretation": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "oneOf": [
                    _directive_schema(
                        "solar_reduction",
                        _adjustment_schema(
                            {"factor": {"type": "number", "minimum": 0, "maximum": 1}},
                            ["factor"],
                        ),
                        True,
                    ),
                    _directive_schema(
                        "minimum_battery_reserve",
                        _adjustment_schema(
                            {"minimum_energy_kwh": {"type": "number", "minimum": 0}},
                            ["minimum_energy_kwh"],
                        ),
                        True,
                    ),
                    _directive_schema("no_charge_window", _adjustment_schema({}, []), True),
                    _directive_schema("no_discharge_window", _adjustment_schema({}, []), True),
                    _directive_schema(
                        "max_grid_window",
                        _adjustment_schema(
                            {"max_grid_kwh": {"type": "number", "minimum": 0}},
                            ["max_grid_kwh"],
                        ),
                        True,
                    ),
                    _directive_schema("no_op", None, False),
                ]
            },
        }
    },
    "required": ["directive_interpretation"],
    "additionalProperties": False,
}


def build_messages(request: OptimizeEnergyRequest) -> list[dict[str, str]]:
    context = {
        "battery_capacity_kwh": request.battery.capacity_kwh,
        "operator_notes": [
            {"note_index": index, "text": note}
            for index, note in enumerate(request.operator_notes)
        ],
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(context, separators=(",", ":"))},
    ]

"""Validated request contract for the optimization endpoint."""

import math
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


NonNegativeFloat = Annotated[float, Field(ge=0)]
HourNumber = Annotated[StrictInt, Field(ge=0, le=23)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HourInput(StrictModel):
    hour: HourNumber
    demand_kwh: NonNegativeFloat
    solar_kwh: NonNegativeFloat
    tariff_bdt_per_kwh: NonNegativeFloat

    @field_validator("demand_kwh", "solar_kwh", "tariff_bdt_per_kwh")
    @classmethod
    def finite_numbers(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("numeric values must be finite")
        return value


class BatteryInput(StrictModel):
    capacity_kwh: NonNegativeFloat
    initial_energy_kwh: NonNegativeFloat
    minimum_energy_kwh: NonNegativeFloat
    max_charge_kwh_per_hour: NonNegativeFloat
    max_discharge_kwh_per_hour: NonNegativeFloat

    @field_validator("*")
    @classmethod
    def finite_numbers(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("numeric values must be finite")
        return value

    @model_validator(mode="after")
    def valid_energy_levels(self) -> "BatteryInput":
        if self.minimum_energy_kwh > self.initial_energy_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed initial_energy_kwh")
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError("initial_energy_kwh cannot exceed capacity_kwh")
        return self


class OptimizeEnergyRequest(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "scenario_id": "SWAGGER-DEMO-01",
                    "operator_notes": [
                        "The campus cultural program was moved to next week."
                    ],
                    "hours": [
                        {
                            "hour": hour,
                            "demand_kwh": 100,
                            "solar_kwh": 0,
                            "tariff_bdt_per_kwh": 10,
                        }
                        for hour in range(24)
                    ],
                    "battery": {
                        "capacity_kwh": 100,
                        "initial_energy_kwh": 50,
                        "minimum_energy_kwh": 20,
                        "max_charge_kwh_per_hour": 25,
                        "max_discharge_kwh_per_hour": 25,
                    },
                }
            ]
        },
    )

    scenario_id: str = Field(min_length=1)
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    hours: list[HourInput] = Field(min_length=24, max_length=24)
    battery: BatteryInput

    @field_validator("scenario_id")
    @classmethod
    def nonblank_scenario_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("scenario_id must not be blank")
        return value

    @field_validator("operator_notes")
    @classmethod
    def nonblank_notes(cls, value: list[str]) -> list[str]:
        if any(not isinstance(note, str) or not note.strip() for note in value):
            raise ValueError("operator_notes must contain non-empty strings")
        return value

    @model_validator(mode="after")
    def complete_hour_set(self) -> "OptimizeEnergyRequest":
        actual = [entry.hour for entry in self.hours]
        if len(set(actual)) != 24 or set(actual) != set(range(24)):
            raise ValueError("hours must uniquely cover integers 0 through 23")
        return self

    def hours_by_number(self) -> list[HourInput]:
        return sorted(self.hours, key=lambda entry: entry.hour)

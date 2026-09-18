"""Successful optimization response models."""

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.models.directives import DirectiveInterpretation


NonNegativeFloat = Annotated[float, Field(ge=0)]


class HourlyPlanEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hour: Annotated[StrictInt, Field(ge=0, le=23)]
    grid_kwh: NonNegativeFloat
    solar_used_kwh: NonNegativeFloat
    battery_action: Literal["charge", "discharge", "idle"]
    battery_kwh: NonNegativeFloat
    battery_energy_after_kwh: NonNegativeFloat

    @field_validator("grid_kwh", "solar_used_kwh", "battery_kwh", "battery_energy_after_kwh")
    @classmethod
    def finite_numbers(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("numeric values must be finite")
        return value

    @model_validator(mode="after")
    def idle_has_zero_magnitude(self) -> "HourlyPlanEntry":
        if self.battery_action == "idle" and self.battery_kwh != 0:
            raise ValueError("idle action requires battery_kwh=0")
        return self


class OptimizeEnergyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanEntry] = Field(min_length=24, max_length=24)
    total_grid_kwh: NonNegativeFloat
    total_cost_bdt: NonNegativeFloat
    peak_grid_kwh: NonNegativeFloat
    plan_summary: str = Field(min_length=1)

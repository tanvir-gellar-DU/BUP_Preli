"""Typed directive interpretation domain."""

import math
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SkipValidation,
    StrictInt,
    field_validator,
    model_validator,
)


DirectiveHour = Annotated[StrictInt, Field(ge=0, le=23)]
FiniteNonNegative = Annotated[float, Field(ge=0)]


class DirectiveType(StrEnum):
    SOLAR_REDUCTION = "solar_reduction"
    MINIMUM_BATTERY_RESERVE = "minimum_battery_reserve"
    NO_CHARGE_WINDOW = "no_charge_window"
    NO_DISCHARGE_WINDOW = "no_discharge_window"
    MAX_GRID_WINDOW = "max_grid_window"
    NO_OP = "no_op"


class Adjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours: list[DirectiveHour] = Field(min_length=1, max_length=24)

    @field_validator("hours")
    @classmethod
    def normalized_hours(cls, value: list[int]) -> list[int]:
        if value != sorted(set(value)):
            raise ValueError("hours must be unique and in ascending order")
        return value


class SolarReductionAdjustment(Adjustment):
    factor: Annotated[float, Field(ge=0, le=1)]

    @field_validator("factor")
    @classmethod
    def finite_factor(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("factor must be finite")
        return value


class MinimumBatteryReserveAdjustment(Adjustment):
    minimum_energy_kwh: FiniteNonNegative

    @field_validator("minimum_energy_kwh")
    @classmethod
    def finite_reserve(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("minimum_energy_kwh must be finite")
        return value


class NoChargeWindowAdjustment(Adjustment):
    pass


class NoDischargeWindowAdjustment(Adjustment):
    pass


class MaxGridWindowAdjustment(Adjustment):
    max_grid_kwh: FiniteNonNegative

    @field_validator("max_grid_kwh")
    @classmethod
    def finite_cap(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("max_grid_kwh must be finite")
        return value


StructuredAdjustment = (
    SolarReductionAdjustment
    | MinimumBatteryReserveAdjustment
    | NoChargeWindowAdjustment
    | NoDischargeWindowAdjustment
    | MaxGridWindowAdjustment
    | None
)


EXPECTED_ADJUSTMENT = {
    DirectiveType.SOLAR_REDUCTION: SolarReductionAdjustment,
    DirectiveType.MINIMUM_BATTERY_RESERVE: MinimumBatteryReserveAdjustment,
    DirectiveType.NO_CHARGE_WINDOW: NoChargeWindowAdjustment,
    DirectiveType.NO_DISCHARGE_WINDOW: NoDischargeWindowAdjustment,
    DirectiveType.MAX_GRID_WINDOW: MaxGridWindowAdjustment,
}


class DirectiveInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_index: Annotated[StrictInt, Field(ge=0)]
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: SkipValidation[StructuredAdjustment]
    explanation: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def parse_adjustment_for_directive(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        try:
            directive_type = DirectiveType(data.get("directive_type"))
        except (TypeError, ValueError):
            return data
        raw_adjustment = data.get("structured_adjustment")
        if directive_type is DirectiveType.NO_OP or raw_adjustment is None:
            return data
        parsed = EXPECTED_ADJUSTMENT[directive_type].model_validate(raw_adjustment)
        return {**data, "structured_adjustment": parsed}

    @model_validator(mode="after")
    def consistent_semantics(self) -> "DirectiveInterpretation":
        if self.directive_type is DirectiveType.NO_OP:
            if self.applies or self.structured_adjustment is not None:
                raise ValueError("no_op requires applies=false and a null adjustment")
            return self

        expected = EXPECTED_ADJUSTMENT[self.directive_type]
        if not self.applies or type(self.structured_adjustment) is not expected:
            raise ValueError(
                f"{self.directive_type.value} requires applies=true and {expected.__name__}"
            )
        return self


class InterpretationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directive_interpretation: list[DirectiveInterpretation]

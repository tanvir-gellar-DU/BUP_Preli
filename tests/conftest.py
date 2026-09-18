from copy import deepcopy

import pytest


@pytest.fixture
def valid_request_data() -> dict:
    return {
        "scenario_id": "TEST-001",
        "operator_notes": ["The cafeteria schedule changed."],
        "hours": [
            {
                "hour": hour,
                "demand_kwh": 10,
                "solar_kwh": 2 if 7 <= hour <= 17 else 0,
                "tariff_bdt_per_kwh": 5,
            }
            for hour in range(24)
        ],
        "battery": {
            "capacity_kwh": 20,
            "initial_energy_kwh": 10,
            "minimum_energy_kwh": 2,
            "max_charge_kwh_per_hour": 5,
            "max_discharge_kwh_per_hour": 5,
        },
    }


@pytest.fixture
def copy_request(valid_request_data: dict):
    def factory() -> dict:
        return deepcopy(valid_request_data)

    return factory

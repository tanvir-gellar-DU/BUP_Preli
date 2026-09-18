from fastapi.testclient import TestClient

from app.api.routes import get_optimization_service
from app.main import create_app
from app.models.directives import DirectiveInterpretation
from app.services.optimization_service import OptimizationService


class NoOpInterpreter:
    async def interpret(self, request):
        return [
            DirectiveInterpretation.model_validate(
                {
                    "note_index": index,
                    "applies": False,
                    "directive_type": "no_op",
                    "structured_adjustment": None,
                    "explanation": "No schedule impact.",
                }
            )
            for index in range(len(request.operator_notes))
        ]


def test_optimize_endpoint_complete_response(copy_request) -> None:
    app = create_app()
    app.dependency_overrides[get_optimization_service] = lambda: OptimizationService(NoOpInterpreter())
    with TestClient(app) as client:
        response = client.post("/optimize-energy", json=copy_request())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "scenario_id", "directive_interpretation", "hourly_plan", "total_grid_kwh",
        "total_cost_bdt", "peak_grid_kwh", "plan_summary",
    }
    assert len(body["hourly_plan"]) == 24
    assert [item["hour"] for item in body["hourly_plan"]] == list(range(24))


def test_structurally_invalid_request_returns_400_without_interpreter(copy_request) -> None:
    data = copy_request()
    data["hours"].pop()
    app = create_app()
    app.dependency_overrides[get_optimization_service] = lambda: OptimizationService(NoOpInterpreter())
    with TestClient(app) as client:
        response = client.post("/optimize-energy", json=data)
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request"}


def test_malformed_json_returns_controlled_400() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/optimize-energy", content="{", headers={"content-type": "application/json"}
        )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request"}


def test_openapi_has_runnable_request_example_and_documents_errors() -> None:
    schema = create_app().openapi()
    request_schema = schema["components"]["schemas"]["OptimizeEnergyRequest"]
    example = request_schema["examples"][0]
    responses = schema["paths"]["/optimize-energy"]["post"]["responses"]

    assert len(example["hours"]) == 24
    assert [entry["hour"] for entry in example["hours"]] == list(range(24))
    assert {"400", "422", "500"} <= responses.keys()

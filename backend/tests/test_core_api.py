from collections.abc import Mapping, Sequence
from typing import cast

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.errors import ApiError
from app.main import create_app


def test_browser_safe_error_details_preserve_public_scalars_and_drop_unsafe_values() -> None:
    long_issue = "x" * 520

    error = ApiError(
        status_code=400,
        code="contract_probe",
        message="Contract probe failed",
        details=cast(
            Sequence[Mapping[str, object]],
            cast(
                object,
                [
                    {
                        "field": "workflowKey",
                        "issue": long_issue,
                        "extensionKey": "signaldeck.finance",
                        "surface": "tool.marketQuote",
                        "retryAfterSeconds": 30,
                        "enabled": False,
                        "ratio": 0.5,
                        "optional": None,
                        "apiKey": "sk-secret",
                        "authorizationHeader": "Bearer token",
                        "exceptionType": "RuntimeError",
                        "debugPayload": {"path": "/home/qing/private.py"},
                        "rawList": ["internal"],
                        "bad-key": "not exposed",
                        1: "not exposed",
                    },
                    "not an object",
                    {"apiKey": "sk-secret"},
                ],
            ),
        ),
    )

    assert error.details == [
        {
            "field": "workflowKey",
            "issue": f"{'x' * 497}...",
            "extensionKey": "signaldeck.finance",
            "surface": "tool.marketQuote",
            "retryAfterSeconds": 30,
            "enabled": False,
            "ratio": 0.5,
            "optional": None,
        }
    ]

    dict_detail_error = ApiError(
        status_code=400,
        code="contract_probe",
        message="Contract probe failed",
        details=cast(
            Sequence[Mapping[str, object]],
            cast(object, {"field": "name", "issue": "invalid"}),
        ),
    )
    text_detail_error = ApiError(
        status_code=400,
        code="contract_probe",
        message="Contract probe failed",
        details=cast(Sequence[Mapping[str, object]], cast(object, "not an array")),
    )

    assert dict_detail_error.details == []
    assert text_detail_error.details == []


def test_removed_workflow_memory_api_is_not_registered() -> None:
    with TestClient(create_app(init_database=False)) as client:
        response = client.get("/api/memory/proposals")

    assert response.status_code == 404
    assert response.json() == {"code": "route_not_found", "message": "Not Found", "details": []}


def test_run_catalog_is_get_only_with_logfire_instrumentation(
    app: FastAPI, client: TestClient
) -> None:
    assert set(app.openapi()["paths"]["/api/runs"]) == {"get"}
    assert client.get("/api/runs").status_code == 200

    # Partial method matches must pass through the real instrumentation as HTTP 405.
    response = client.post("/api/runs")

    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert response.json() == {
        "code": "method_not_allowed",
        "message": "Method Not Allowed",
        "details": [],
    }


def test_other_framework_http_errors_use_the_api_error_envelope() -> None:
    app = create_app(init_database=False)

    def http_error_probe() -> None:
        raise HTTPException(status_code=409, detail="Probe conflict", headers={"Retry-After": "1"})

    app.add_api_route("/__test/http-error", http_error_probe, methods=["GET"])

    with TestClient(app) as test_client:
        response = test_client.get("/__test/http-error")

    assert response.status_code == 409
    assert response.headers["retry-after"] == "1"
    assert response.json() == {"code": "http_error", "message": "Probe conflict", "details": []}


def test_api_error_envelope_details_are_browser_safe() -> None:
    app = create_app(init_database=False)

    def api_error_details_probe() -> None:
        raise ApiError(
            status_code=400,
            code="contract_probe",
            message="Contract probe failed",
            details=[
                {
                    "field": "workflowKey",
                    "issue": "Unknown workflow",
                    "extensionKey": "signaldeck.digital_oracle",
                    "surface": "tool.predictionMarkets",
                    "retryAfterSeconds": 15,
                    "apiKey": "sk-secret",
                    "exceptionType": "RuntimeError",
                    "debugPayload": {"path": "/home/qing/private.py"},
                }
            ],
        )

    app.add_api_route("/__test/api-error-details", api_error_details_probe, methods=["GET"])

    with TestClient(app) as test_client:
        response = test_client.get("/__test/api-error-details")

    assert response.status_code == 400
    assert response.json() == {
        "code": "contract_probe",
        "message": "Contract probe failed",
        "details": [
            {
                "field": "workflowKey",
                "issue": "Unknown workflow",
                "extensionKey": "signaldeck.digital_oracle",
                "surface": "tool.predictionMarkets",
                "retryAfterSeconds": 15,
            }
        ],
    }

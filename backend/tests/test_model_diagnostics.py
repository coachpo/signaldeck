"""Safe provider categories and offline, revision-bound call observations."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from app.domain.execution import ExecutionEvidence
from app.domain.model_diagnostics import model_binding_digest
from app.infrastructure.model_runtime import model_failure
from tests.test_task_experience import configured
from tests.test_task_experience import platform as platform_fixture

platform = platform_fixture


@pytest.mark.parametrize(
    "status,code,category",
    [
        (400, "insufficient_user_quota", "quota"),
        (429, "insufficient_quota", "quota"),
        (401, "malicious-secret", "authentication"),
        (429, "rate_limit_exceeded", "rate_limit"),
        (404, "model_not_found", "model"),
        (400, "context_length_exceeded", "input"),
        (400, "malicious-secret", "unknown"),
        (500, None, "unknown"),
    ],
)
def test_safe_http_categories(status, code, category):
    failure = model_failure(
        ModelHTTPError(
            status,
            "secret-model",
            {
                "error": {
                    "code": code,
                    "message": "malicious-secret insufficient_quota invalid_api_key",
                    "headers": {"Authorization": "secret"},
                }
            },
        )
    )
    assert failure[0] == "model_http_error"
    assert failure[2] == {
        "failureType": "http_error",
        "httpStatus": status,
        "errorCategory": category,
    }
    assert "secret" not in json.dumps(failure)


@pytest.mark.parametrize(
    "body", [None, "insufficient_quota", {"error": []}, {"error": {"code": ["insufficient_quota"]}}]
)
def test_malformed_provider_body_is_unknown(body):
    assert model_failure(ModelHTTPError(400, "model", body))[2]["errorCategory"] == "unknown"


@pytest.mark.parametrize(
    "code,category",
    [("model_http_error", "quota"), ("model_output_limit_exceeded", "output_limit")],
)
def test_observations_are_offline_and_bound_to_frozen_identity(platform, code, category):
    client, store, _ = platform
    configured(client, store, model=True)
    launched = client.post(
        "/api/workflow-packages/api-package/launches",
        json={"workflowKey": "main", "parameters": {"text": "hello"}, "launchId": "diagnostics"},
    ).json()
    run = store.get_run(launched["id"])
    binding = run.spec.model_bindings["local-model"]
    now = datetime.now(UTC)
    store.record_evidence_batch(
        [
            ExecutionEvidence(
                id="node", run_id=run.id, node_id="echo", kind="node", status="running"
            ),
            ExecutionEvidence(
                id="agent",
                run_id=run.id,
                node_id="echo",
                parent_id="node",
                kind="agent",
                status="running",
            ),
            ExecutionEvidence(
                id="model",
                run_id=run.id,
                node_id="echo",
                parent_id="agent",
                kind="model",
                status="running",
            ),
        ]
    )
    base = dict(
        parent_id="model",
        run_id=run.id,
        node_id="echo",
        kind="attempt",
        status="failed",
        started_at=now,
        finished_at=now,
        error_code=code,
    )
    # The old request remains an unknown cause and cannot be reclassified.
    store.record_evidence(
        ExecutionEvidence(
            id="old", **base, metadata={"networkKind": "model_request", "httpStatus": 400}
        )
    )

    def observation():
        resources = client.get("/api/resources").json()["items"]
        return resources[0]["modelObservation"]

    assert observation()["status"] == "not_observed"
    metadata = {
        "networkKind": "model_request",
        "resourceId": "local-model",
        "modelBindingDigest": model_binding_digest(binding),
        "errorCategory": category,
        "httpStatus": 400,
    }
    store.record_evidence(ExecutionEvidence(id="confirmed", **base, metadata=metadata))
    assert observation()["errorCategory"] == category
    assert observation()["errorCode"] == code
    prepared = client.post(
        "/api/workflow-packages/api-package/prepare",
        json={"workflowKey": "main", "parameters": {"text": "hello"}},
    ).json()
    assert (
        next(r for r in prepared["requirements"] if r["kind"] == "model")["modelObservation"]
        == observation()
    )
    # A success without usage is still a confirmed call, never a token-count guess.
    store.record_evidence(
        ExecutionEvidence(
            id="success",
            **{
                **base,
                "status": "succeeded",
                "error_code": None,
                "finished_at": now + timedelta(seconds=1),
            },
            metadata={
                k: v for k, v in metadata.items() if k not in {"errorCategory", "httpStatus"}
            },
        )
    )
    assert observation()["status"] == "succeeded"
    assert observation()["errorCategory"] is None
    original = store.get_resource("local-model")["config"]
    for key, value in [
        ("modelId", "other"),
        ("baseUrl", "http://127.0.0.1:2"),
        ("apiStyle", "responses"),
    ]:
        store.save_resource("local-model", "model", {**original, key: value})
        assert observation()["status"] == "not_observed"
    store.save_resource("local-model", "model", original)
    assert observation()["status"] == "succeeded"
    store.save_resource("local-model", "model", original, {"apiKey": "rotated-secret"})
    assert observation()["status"] == "not_observed"
    assert "rotated-secret" not in json.dumps(client.get("/api/resources").json())
    assert (
        next(e for e in store.get_run(run.id).evidence if e.id == "old").metadata.get(
            "errorCategory"
        )
        is None
    )


@pytest.mark.parametrize(
    "code,category",
    [("model_http_error", "quota"), ("model_output_limit_exceeded", "output_limit")],
)
def test_result_category_follows_failed_node_and_not_recovered_attempt(platform, code, category):
    from app.application.result_projection import project_result

    client, store, _ = platform
    configured(client, store, model=True)
    launch = client.post(
        "/api/workflow-packages/api-package/launches",
        json={"workflowKey": "main", "parameters": {"text": "hi"}, "launchId": "failed-result"},
    ).json()
    run = store.get_run(launch["id"])
    run.status, run.error_code = "failed", "workflow_nodes_failed"
    run.evidence = [
        ExecutionEvidence(
            id="node",
            run_id=run.id,
            node_id="echo",
            kind="node",
            status="failed",
            error_code=code,
        ),
        ExecutionEvidence(
            id="model",
            run_id=run.id,
            node_id="echo",
            kind="model",
            status="failed",
            error_code=code,
            metadata={"errorCategory": category},
        ),
    ]
    assert project_result(run).error_category == category
    run.evidence[1].metadata = {}
    assert project_result(run).error_category is None
    run.evidence[1].metadata = {"errorCategory": category}
    run.evidence[0].status = "succeeded"
    assert project_result(run).error_category is None

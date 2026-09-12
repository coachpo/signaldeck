"""Readable result diagnostics retain model-contact facts and failed-step ownership."""

import pytest

from app.application.result_projection import project_result
from app.domain.execution import ExecutionEvidence
from tests.test_result_declarations import run_fixture


def invalid_output_run(node_code="agent_output_invalid"):
    run = run_fixture()
    run.status, run.error_code = "failed", "workflow_nodes_failed"
    run.spec.definition["agents"]["echo"]["strategy"] = {
        "kind": "model",
        "modelRef": "local-model",
        "prompt": "Follow the requested result requirements.",
    }
    run.evidence = [
        ExecutionEvidence(
            id="node-final",
            run_id=run.id,
            node_id="echo",
            kind="node",
            status="failed",
            error_code=node_code,
        ),
        ExecutionEvidence(
            id="agent-final",
            parent_id="node-final",
            run_id=run.id,
            node_id="echo",
            kind="agent",
            status="failed",
            error_code="agent_output_invalid",
        ),
        ExecutionEvidence(
            id="model-reply",
            parent_id="agent-final",
            run_id=run.id,
            node_id="echo",
            kind="model",
            status="succeeded",
            output="Unusable model reply, retained exactly as recorded.",
            metadata={"inputTokens": 20, "outputTokens": 10},
        ),
    ]
    return run


@pytest.mark.parametrize("node_code", ["agent_output_invalid", "node_execution_failed"])
def test_failed_result_reports_known_output_problem_without_rewriting_model_contact(node_code):
    run = invalid_output_run(node_code)
    before = run.model_dump(mode="json", by_alias=True)
    result = project_result(run)
    assert result.model_dump(mode="json", by_alias=True)["errorCode"] == "agent_output_invalid"
    assert result.status == "failed" and result.error_category is None
    assert result.body is None and result.sections == []
    assert result.content_status == "not_available"
    assert run.model_dump(mode="json", by_alias=True) == before


def test_known_output_failure_preserves_previously_confirmed_declared_body():
    run = invalid_output_run()
    workflow = run.spec.definition["workflows"]["main"]
    workflow["nodes"]["earlier"] = {"uses": "echo", "inputMapping": {"ref": "workflow.input"}}
    workflow["presentation"]["sections"] = [
        {"kind": "markdown", "label": "已确认正文", "ref": "nodes.earlier.output.text"}
    ]
    run.evidence.append(
        ExecutionEvidence(
            id="earlier-node",
            run_id=run.id,
            node_id="earlier",
            kind="node",
            status="succeeded",
            output={"text": "Original confirmed body and code: schema = 42;"},
        )
    )
    result = project_result(run)
    assert result.error_code == "agent_output_invalid"
    assert result.body == "Original confirmed body and code: schema = 42;"
    assert result.content_status == "partial"


def test_recovered_output_attempt_does_not_explain_another_terminal_failure():
    run = invalid_output_run()
    run.evidence.append(
        ExecutionEvidence(
            id="node-recovered",
            run_id=run.id,
            node_id="echo",
            kind="node",
            status="succeeded",
            attempt=2,
            output={"text": "Recovered answer"},
        )
    )
    run.evidence.append(
        ExecutionEvidence(
            id="other-failure",
            run_id=run.id,
            node_id="other",
            kind="node",
            status="failed",
            error_code="resource_unavailable",
        )
    )
    assert project_result(run).error_code == "workflow_nodes_failed"


@pytest.mark.parametrize(
    "status,code", [("cancelled", "run_cancelled"), ("failed", "resource_unavailable")]
)
def test_specific_terminal_reason_is_not_replaced_by_an_unrelated_output_failure(status, code):
    run = invalid_output_run()
    run.status, run.error_code = status, code
    assert project_result(run).error_code == code

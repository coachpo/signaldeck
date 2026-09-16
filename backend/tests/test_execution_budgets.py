"""Execution budgets are reviewed intent, separate from package identity."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.domain.budgets import BudgetOverride, ExecutionOptions, resolve_agent_budgets
from app.domain.compiler import compile_package
from app.domain.definitions import Budget
from app.domain.execution import ApplicationError
from app.domain.tool_contracts import canonical_digest
from app.infrastructure.platform_models import RunRow
from app.infrastructure.temporal_dispatch import TemporalRunEngine
from tests.test_dag_compiler import package
from tests.test_task_experience import configured
from tests.test_task_experience import platform as platform_fixture

platform = platform_fixture


@pytest.mark.parametrize("value", [None, 0, -1, True, 1.5, "100"])
@pytest.mark.parametrize("field", ["maxTokens", "maxOutputTokens"])
def test_budget_sentinels_are_explicit(field, value):
    for model in (Budget, BudgetOverride):
        with pytest.raises(ValidationError):
            model.model_validate({field: value})


def test_partial_overrides_resolve_without_mutating_package():
    compiled = compile_package(package())
    before = compiled.package.model_dump(mode="json", by_alias=True)
    options = ExecutionOptions.model_validate(
        {
            "agentBudgets": {
                "echo": {"maxTokens": "unlimited", "maxOutputTokens": "provider_default"}
            }
        }
    )
    resolved = resolve_agent_budgets(compiled.package, "main", options)
    assert resolved["echo"].max_tokens == "unlimited"
    assert resolved["echo"].max_output_tokens == "provider_default"
    assert resolved["echo"].max_model_requests == 12
    assert compiled.package.model_dump(mode="json", by_alias=True) == before
    with pytest.raises(ApplicationError, match="unavailable"):
        resolve_agent_budgets(
            compiled.package,
            "main",
            ExecutionOptions(agent_budgets={"removed": BudgetOverride(max_tokens=10)}),
        )


def test_review_identity_and_frozen_package_are_budget_aware(platform):
    client, store, _ = platform
    configured(client, store, model=True)
    base = {"workflowKey": "main", "parameters": {"text": "hello"}}
    override = {
        "agentBudgets": {"echo": {"maxTokens": "unlimited", "maxOutputTokens": "provider_default"}}
    }
    prepared = client.post(
        "/api/workflow-packages/api-package/prepare", json={**base, "executionOptions": override}
    )
    assert prepared.status_code == 200, prepared.text
    review = prepared.json()
    assert review["effectiveSettings"]["agents"]["echo"]["budgetSources"]["maxTokens"] == "task"
    request = {
        **base,
        "executionOptions": override,
        "bindingToken": review["bindingToken"],
        "launchId": "budget-intent",
    }
    rejected = client.post(
        "/api/workflow-packages/api-package/launches", json={**request, "executionOptions": {}}
    )
    assert rejected.status_code == 409
    launched = client.post("/api/workflow-packages/api-package/launches", json=request)
    assert launched.status_code == 201, launched.text
    original = store.get_run(launched.json()["id"])
    assert original.spec.effective_agent_budgets["echo"].max_tokens == "unlimited"
    assert original.spec.definition["agents"]["echo"]["budget"]["maxTokens"] == 100000
    assert original.package_hash == review["packageHash"]
    assert (
        client.post("/api/workflow-packages/api-package/launches", json=request).json()["id"]
        == original.id
    )
    conflict = client.post(
        "/api/workflow-packages/api-package/launches", json={**request, "executionOptions": {}}
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "launch_identity_conflict"


def test_historical_snapshot_redelivery_keeps_original_memo_hash(platform):
    client, store, _ = platform
    configured(client, store, model=True)
    request = {"workflowKey": "main", "parameters": {"text": "hello"}, "launchId": "legacy-budget"}
    launched = client.post("/api/workflow-packages/api-package/launches", json=request)
    assert launched.status_code == 201
    run_id = launched.json()["id"]
    with store.session_factory() as session, session.begin():
        row = session.get(RunRow, run_id)
        # Simulate the exact persisted shape and Temporal memo from before this feature.
        historical = dict(row.spec)
        assert historical["effectiveAgentBudgets"]["echo"]["maxOutputTokens"] == "auto"
        assert "executionOptions" not in historical
        historical.pop("effectiveAgentBudgets")
        row.spec = historical
    original_hash = canonical_digest(historical)
    read = client.get(f"/api/runs/{run_id}")
    assert read.status_code == 200
    assert read.json()["spec"] == historical
    assert store.get_run(run_id).spec.model_dump(mode="json", by_alias=True) == historical
    # Lost response retries retain their old launch identity and immutable JSON.
    assert (
        client.post("/api/workflow-packages/api-package/launches", json=request).json()["id"]
        == run_id
    )
    assert store.get_run(run_id).spec.model_dump(mode="json", by_alias=True) == historical
    description = SimpleNamespace(memo_value=AsyncMock(return_value=original_hash))
    handle = SimpleNamespace(describe=AsyncMock(return_value=description))
    temporal = SimpleNamespace(get_workflow_handle=lambda _: handle, start_workflow=AsyncMock())
    asyncio.run(TemporalRunEngine(temporal).start(store.get_run(run_id).spec))
    temporal.start_workflow.assert_not_called()


@pytest.mark.parametrize("action", ["rerun", "reuse"])
def test_historical_repeat_retry_preserves_accepted_intent(platform, action):
    client, store, _ = platform
    configured(client, store, model=True)
    initial = client.post(
        "/api/workflow-packages/api-package/launches",
        json={"workflowKey": "main", "parameters": {"text": "hello"}},
    ).json()
    request = {"launchId": "legacy-repeat"}
    if action == "reuse":
        request["parameters"] = {"text": "reused"}
    endpoint = f"/api/runs/{initial['id']}/{action}"
    repeated = client.post(endpoint, json=request)
    assert repeated.status_code == 201
    run_id = repeated.json()["id"]
    with store.session_factory() as session, session.begin():
        row = session.get(RunRow, run_id)
        historical = dict(row.spec)
        historical.pop("executionOptions")
        historical.pop("effectiveAgentBudgets")
        row.spec = historical
        row.launch_digest = canonical_digest(
            {key: historical[key] for key in ("packageKey", "workflowKey", "parameters", "origin")}
        )
    # No resource resolution is allowed while recovering this accepted identity.
    store.get_resource = lambda _: pytest.fail("Retry resolved mutable configuration")
    retry = client.post(endpoint, json=request)
    assert retry.status_code == 201, retry.text
    assert retry.json()["id"] == run_id
    assert store.get_run(run_id).spec.model_dump(mode="json", by_alias=True) == historical
    if action == "reuse":
        conflict = client.post(
            endpoint,
            json={**request, "executionOptions": {"agentBudgets": {"echo": {"maxTokens": 20}}}},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "launch_identity_conflict"

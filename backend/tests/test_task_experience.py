"""Ordinary task boundaries retain canonical execution and historical facts."""

import json

import pytest
from fastapi.testclient import TestClient

from app.api.platform_dependencies import get_artifacts, get_launch_service, get_platform_store
from app.application.launch import LaunchService
from app.domain.execution import ExecutionEvidence
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.main import create_app
from tests.test_platform_api import FixedCore, release, source


@pytest.fixture
def platform(session_factory, tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts", inline_threshold=4096)
    store = PlatformStore(session_factory, artifacts)
    store.initialize()
    app = create_app(init_database=False)
    app.dependency_overrides[get_platform_store] = lambda: store
    app.dependency_overrides[get_launch_service] = lambda: LaunchService(store, FixedCore())
    app.dependency_overrides[get_artifacts] = lambda: artifacts
    with TestClient(app) as client:
        yield client, store, artifacts


def configured(client, store, *, model=False):
    client.post("/api/workflow-packages", json={"manifestSource": source(model=model)})
    store.install_plugin("example/echo", release())
    if model:
        store.save_resource(
            "local-model",
            "model",
            {
                "baseUrl": "http://127.0.0.1:1",
                "modelId": "controlled",
            },
            {"apiKey": "never-public"},
        )


def test_prepare_missing_service_and_no_secret_or_probe(platform):
    client, store, _ = platform
    client.post("/api/workflow-packages", json={"manifestSource": source(model=True)})
    response = client.post(
        "/api/workflow-packages/api-package/prepare",
        json={
            "workflowKey": "main",
            "parameters": {"text": "hello"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is False and data["bindingToken"] is None
    assert {r["id"] for r in data["requirements"] if not r["configured"]} == {
        "local-model",
        "example/echo",
    }
    configured(client, store, model=True)
    data = client.post(
        "/api/workflow-packages/api-package/prepare",
        json={
            "workflowKey": "main",
            "parameters": {"text": "hello"},
        },
    ).json()
    assert data["ready"] is True
    assert all(r["observation"] == "not_observed" for r in data["requirements"])
    assert "never-public" not in json.dumps(data)
    assert store.list_runs() == []


def test_review_token_rejects_changed_binding_and_retry_keeps_identity(platform):
    client, store, _ = platform
    configured(client, store, model=True)
    request = {"workflowKey": "main", "parameters": {"text": "hello"}}
    prepared = client.post("/api/workflow-packages/api-package/prepare", json=request).json()
    store.save_resource(
        "local-model", "model", {"baseUrl": "http://127.0.0.1:1", "modelId": "different"}
    )
    launch = {**request, "bindingToken": prepared["bindingToken"], "launchId": "reviewed-start"}
    response = client.post("/api/workflow-packages/api-package/launches", json=launch)
    assert response.status_code == 409 and response.json()["code"] == "binding_changed"
    assert store.list_runs() == []
    prepared = client.post("/api/workflow-packages/api-package/prepare", json=request).json()
    launch["bindingToken"] = prepared["bindingToken"]
    accepted = client.post("/api/workflow-packages/api-package/launches", json=launch).json()
    store.set_plugin_enabled("example/echo", False)
    retried = client.post("/api/workflow-packages/api-package/launches", json=launch)
    assert retried.status_code == 201 and retried.json()["id"] == accepted["id"]
    assert len(store.list_runs()) == 1


def test_preparation_summary_matches_token_during_resource_update(platform, monkeypatch):
    client, store, _ = platform
    configured(client, store, model=True)
    original_get = store.get_resource
    changed = False

    def rotate_after_read(resource_id):
        nonlocal changed
        record = original_get(resource_id)
        if resource_id == "local-model" and not changed:
            changed = True
            store.save_resource(
                resource_id, "model", {"baseUrl": "http://127.0.0.1:1", "modelId": "updated"}
            )
        return record

    monkeypatch.setattr(store, "get_resource", rotate_after_read)
    request = {"workflowKey": "main", "parameters": {"text": "reviewed"}}
    prepared = client.post("/api/workflow-packages/api-package/prepare", json=request).json()
    launched = client.post(
        "/api/workflow-packages/api-package/launches",
        json={**request, "launchId": "consistent-review", "bindingToken": prepared["bindingToken"]},
    )
    if launched.status_code == 409:
        assert launched.json()["code"] == "binding_changed"
        assert store.list_runs() == []
    else:
        assert launched.status_code == 201, launched.text
        reviewed = next(item for item in prepared["requirements"] if item["kind"] == "model")
        actual = store.get_run(launched.json()["id"]).spec.model_bindings["local-model"]
        assert reviewed["config"]["modelId"] == actual["modelId"]


@pytest.mark.parametrize("package_change", ["unavailable", "schema"])
def test_schedule_creation_retry_uses_persisted_request_before_current_package_validation(
    platform, monkeypatch, package_change
):
    from types import SimpleNamespace

    from app.api import platform_schedules
    from app.infrastructure.schedule_store import ScheduleStore

    client, store, _ = platform
    configured(client, store)
    schedules = ScheduleStore(store.session_factory)
    schedules.initialize()

    async def save(definition, identity=None, *, create_only=False):
        return schedules.save(definition, identity, create_only=create_only)

    client.app.dependency_overrides[platform_schedules.get_schedule_service] = (
        lambda: SimpleNamespace(store=schedules, save=save)
    )
    monkeypatch.setattr(platform_schedules, "get_platform_store", lambda: store)
    request = {
        "name": "Reviewed schedule",
        "packageKey": "api-package",
        "workflowKey": "main",
        "parameters": {"text": "accepted input"},
        "cron": "0 9 * * *",
        "requestId": "persisted-creation",
    }
    original = client.post("/api/schedules", json=request)
    assert original.status_code == 201, original.text
    if package_change == "unavailable":
        monkeypatch.setattr(store, "get_package", lambda *args, **kwargs: None)
    else:
        updated = json.loads(source())
        updated["workflows"]["main"]["inputSchema"]["properties"]["text"]["maxLength"] = 2
        assert (
            client.patch(
                "/api/workflow-packages/api-package", json={"manifestSource": json.dumps(updated)}
            ).status_code
            == 200
        )
    retried = client.post("/api/schedules", json=request)
    assert retried.status_code == 201, retried.text
    assert retried.json()["id"] == original.json()["id"]
    assert retried.json()["revision"] == 1
    assert len(schedules.list()) == 1
    conflict = client.post("/api/schedules", json={**request, "name": "Different intent"})
    assert conflict.status_code == 409 and conflict.json()["code"] == "schedule_identity_conflict"


def test_reuse_pins_original_revision_preserves_output_and_tracks_source(platform):
    client, store, _ = platform
    configured(client, store)
    original = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "original"},
            "launchId": "original",
        },
    ).json()
    store.project_run(original["id"], "succeeded", {"text": "immutable result"})
    changed = json.loads(source())
    changed["metadata"]["name"] = "New mutable name"
    client.patch("/api/workflow-packages/api-package", json={"manifestSource": json.dumps(changed)})
    reusable = client.get(f'/api/runs/{original["id"]}/reuse').json()
    assert reusable["parameters"] == {"text": "original"}
    assert reusable["packageHash"] == original["packageHash"]
    new = client.post(
        f'/api/runs/{original["id"]}/reuse',
        json={
            "parameters": {"text": "edited"},
            "launchId": "edited",
        },
    ).json()
    assert new["origin"] == {
        "kind": "reuse",
        "sourceRunId": original["id"],
        "scheduleId": None,
        "triggerId": None,
        "scheduledAt": None,
    }
    assert new["packageHash"] == original["packageHash"]
    assert new["title"] == original["title"] == "API Package"
    assert client.get(f'/api/runs/{original["id"]}').json()["output"] == {
        "text": "immutable result"
    }


def test_global_history_pages_literal_search_and_insert_watermark(platform):
    client, store, _ = platform
    configured(client, store)
    ids = []
    for i in range(5):
        run = client.post(
            "/api/workflow-packages/api-package/launches",
            json={
                "workflowKey": "main",
                "parameters": {"text": str(i)},
                "launchId": str(i),
            },
        ).json()
        ids.append(run["id"])
        store.project_run(run["id"], "succeeded", {"text": f"record {i}%"})
    first = client.get("/api/runs", params={"limit": 2, "sort": "created_asc", "q": "%"}).json()
    assert first["total"] == 5 and len(first["items"]) == 2
    client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "new"},
            "launchId": "new",
        },
    )
    second = client.get(
        "/api/runs",
        params={"limit": 2, "offset": 2, "sort": "created_asc", "snapshotAt": first["snapshotAt"]},
    ).json()
    assert second["total"] == 5
    assert [r["id"] for r in second["items"]] == ids[2:4]
    assert client.get("/api/runs", params={"status": "queued"}).json()["total"] == 1


def test_result_keeps_cancel_request_and_unknown_separate_from_content(platform):
    client, store, _ = platform
    configured(client, store)
    run = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "hello"},
            "launchId": "result",
        },
    ).json()
    store.project_run(run["id"], "running")
    store.request_cancel(run["id"])
    result = client.get(f'/api/runs/{run["id"]}/result').json()
    assert result["status"] == "running" and result["cancelRequestedAt"]
    assert result["contentStatus"] == "not_available"
    from app.application.result_projection import project_result

    detail = store.get_run(run["id"])
    detail.output = {"text": "confirmed prior output", "sources": [{"name": "controlled source"}]}
    detail.evidence = [
        ExecutionEvidence(
            id="unknown-op", run_id=detail.id, node_id="write", kind="tool", status="unknown"
        )
    ]
    result = project_result(detail)
    assert result.body == "confirmed prior output" and result.content_status == "unknown"
    assert result.unknown_evidence_ids == ["unknown-op"]
    assert result.sources == [{"name": "controlled source"}]


def test_deployment_connection_choices_validate_and_never_expose_credentials(
    platform, monkeypatch, tmp_path
):
    client, _, _ = platform
    monkeypatch.delenv("SIGNALDECK_CONNECTION_PRESETS_FILE", raising=False)
    assert client.get("/api/connection-presets").json() == {"items": []}
    path = tmp_path / "connections.json"
    data = {
        "items": [
            {
                "id": "local",
                "name": "受控模型",
                "resourceId": "research-model",
                "kind": "model",
                "config": {"baseUrl": "http://127.0.0.1:18081/v1", "modelId": "controlled"},
                "credentialFields": [{"key": "apiKey", "label": "访问密钥", "required": False}],
            }
        ]
    }
    path.write_text(json.dumps(data))
    monkeypatch.setenv("SIGNALDECK_CONNECTION_PRESETS_FILE", str(path))
    result = client.get("/api/connection-presets")
    assert result.status_code == 200 and result.json()["items"][0]["resourceId"] == "research-model"
    data["items"][0]["config"]["apiKey"] = "must-stay-private"
    path.write_text(json.dumps(data))
    result = client.get("/api/connection-presets")
    assert result.status_code == 503 and "must-stay-private" not in result.text


def test_history_uses_frozen_workflow_name_for_search_and_sort(platform):
    client, store, _ = platform
    configured(client, store)
    definition = json.loads(source())
    definition["workflows"]["main"]["name"] = "业务任务标题"
    client.patch(
        "/api/workflow-packages/api-package", json={"manifestSource": json.dumps(definition)}
    )
    original = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "test"},
            "launchId": "named",
        },
    ).json()
    data = client.get("/api/runs", params={"q": "业务任务标题", "sort": "title_asc"}).json()
    assert data["total"] == 1 and data["items"][0]["title"] == original["title"] == "业务任务标题"


def test_prepare_rejects_unrelated_comparison_source(platform):
    client, store, _ = platform
    configured(client, store)
    original = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "original"},
            "launchId": "source",
        },
    ).json()
    client.post("/api/workflow-packages", json={"manifestSource": source("other")})
    result = client.post(
        "/api/workflow-packages/other/prepare",
        json={
            "workflowKey": "main",
            "parameters": {"text": "new"},
            "sourceRunId": original["id"],
        },
    )
    assert result.status_code == 409 and result.json()["code"] == "source_task_mismatch"


def test_result_links_confirmed_owner_and_does_not_mistake_recovered_attempt_for_unknown(platform):
    client, store, _ = platform
    configured(client, store)
    record = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "test"},
            "launchId": "linked",
        },
    ).json()
    from app.application.result_projection import project_result

    detail = store.get_run(record["id"])
    receipt = {"reportId": 7, "name": "报告"}
    detail.output = receipt
    detail.status = "succeeded"
    detail.evidence = [
        ExecutionEvidence(
            id="lost-response", run_id=detail.id, node_id="save", kind="attempt", status="unknown"
        ),
        ExecutionEvidence(
            id="confirmed-write",
            run_id=detail.id,
            node_id="save",
            kind="tool",
            tool_id="example/echo/copy",
            status="succeeded",
            output=receipt,
        ),
    ]
    projected = project_result(detail)
    assert projected.content_status == "available"
    assert projected.unknown_evidence_ids == []
    assert len(projected.attachments) == 1
    assert projected.attachments[0].plugin_id == "example/echo"
    assert projected.attachments[0].evidence_id == "confirmed-write"


def test_launch_identity_does_not_accept_different_explicit_revision(platform):
    client, store, _ = platform
    configured(client, store)
    first = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "test"},
            "launchId": "revision-choice",
        },
    ).json()
    changed = json.loads(source())
    changed["metadata"]["name"] = "Revised"
    second_revision = client.patch(
        "/api/workflow-packages/api-package", json={"manifestSource": json.dumps(changed)}
    ).json()
    result = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "test"},
            "launchId": "revision-choice",
            "revisionHash": second_revision["packageHash"],
        },
    )
    assert result.status_code == 409 and result.json()["code"] == "launch_identity_conflict"
    retry = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "test"},
            "launchId": "revision-choice",
            "revisionHash": first["packageHash"],
        },
    )
    assert retry.status_code == 201 and retry.json()["id"] == first["id"]


def test_history_title_fallback_preserves_non_string_and_whitespace_inputs(platform):
    client, store, _ = platform
    configured(client, store)
    record = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "test"},
            "launchId": "base-title",
        },
    ).json()
    spec = store.get_run(record["id"]).spec
    for identity, parameters in (
        ("whitespace", {"title": " \n\t", "question": "  查询标题  "}),
        ("number", {"title": 123, "question": "数字字段不作标题"}),
    ):
        store.create_run(
            spec.model_copy(update={"run_id": identity, "parameters": parameters}), identity
        )
    for term, identity in (("查询标题", "whitespace"), ("数字字段不作标题", "number")):
        result = client.get("/api/runs", params={"q": term, "sort": "title_asc"}).json()
        assert result["total"] == 1 and result["items"][0]["id"] == identity
        assert result["items"][0]["title"] == term


@pytest.mark.parametrize("large_tool_output", [False, True])
def test_finance_receipt_owner_follows_frozen_deterministic_mapping(platform, large_tool_output):
    from pathlib import Path

    from app.application.result_projection import project_result
    from app.domain.definition_parser import parse_package_source

    client, store, artifacts = platform
    configured(client, store)
    record = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "test"},
            "launchId": "mapped-owner",
        },
    ).json()
    detail = store.get_run(record["id"])
    definition = parse_package_source(
        (Path(__file__).parents[2] / "demo/digital_oracle_researcher.yaml").read_text()
    ).package
    detail.spec.definition = definition.model_dump(mode="json", by_alias=True)
    detail.workflow_key = "research"
    detail.status = "succeeded"
    detail.output = {"reportId": 7, "name": "保存后的报告"}
    tool_output = {"id": 7, "slug": "report-7", "name": "保存后的报告", "content": "正文"}
    if large_tool_output:
        from app.infrastructure.evidence_payloads import persist_value

        tool_output["content"] *= 5000
        tool_output = persist_value(tool_output, artifacts)
        assert "$artifact" in tool_output
    detail.evidence = [
        ExecutionEvidence(
            id="report-tool",
            run_id=detail.id,
            node_id="save",
            kind="tool",
            tool_id="signaldeck/finance/reports_create",
            status="succeeded",
            output=tool_output,
        ),
        ExecutionEvidence(
            id="save-node",
            run_id=detail.id,
            node_id="save",
            kind="node",
            status="succeeded",
            output=detail.output,
        ),
    ]
    report = next(item for item in project_result(detail).attachments if item.kind == "report")
    assert report.reference["reportId"] == 7
    assert report.plugin_id == "signaldeck/finance" and report.evidence_id == "report-tool"


def test_attention_group_and_summary_use_logical_unknown_not_old_network_attempt(platform):
    client, store, _ = platform
    configured(client, store)
    record = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "test"},
            "launchId": "attention",
        },
    ).json()
    run_id = record["id"]
    store.record_evidence_batch(
        [
            ExecutionEvidence(
                id="node", run_id=run_id, node_id="echo", kind="node", status="running"
            ),
            ExecutionEvidence(
                id="agent",
                run_id=run_id,
                parent_id="node",
                node_id="echo",
                kind="agent",
                status="running",
            ),
            ExecutionEvidence(
                id="tool",
                run_id=run_id,
                parent_id="agent",
                node_id="echo",
                kind="tool",
                tool_id="example/echo/copy",
                status="unknown",
            ),
            ExecutionEvidence(
                id="attempt",
                run_id=run_id,
                parent_id="tool",
                node_id="echo",
                kind="attempt",
                status="unknown",
            ),
        ]
    )
    history = client.get("/api/runs", params={"group": "attention"}).json()
    assert history["total"] == 1 and history["items"][0]["hasUnknownEffects"] is True
    assert client.get(f"/api/runs/{run_id}").json()["hasUnknownEffects"] is True
    store.record_evidence(
        ExecutionEvidence(
            id="tool",
            run_id=run_id,
            parent_id="agent",
            node_id="echo",
            kind="tool",
            tool_id="example/echo/copy",
            status="succeeded",
            output={"text": "confirmed"},
        )
    )
    assert client.get("/api/runs", params={"group": "attention"}).json()["total"] == 0
    assert client.get(f"/api/runs/{run_id}").json()["hasUnknownEffects"] is False


def test_result_preserves_structured_source_warnings(platform):
    from app.application.result_projection import project_result

    client, store, _ = platform
    configured(client, store)
    record = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "test"},
            "launchId": "warnings",
        },
    ).json()
    detail = store.get_run(record["id"])
    detail.output = {
        "text": "报告正文",
        "warnings": [{"code": "controlled", "message": "此来源为受控本地数据"}],
    }
    detail.status = "succeeded"
    result = project_result(detail)
    assert result.content_status == "partial" and result.missing == ["此来源为受控本地数据"]


def test_preparation_reports_last_failed_observation_without_claiming_live_health(platform):
    from datetime import UTC, datetime

    client, store, _ = platform
    configured(client, store)
    record = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": "test"},
            "launchId": "observed",
        },
    ).json()
    run_id = record["id"]
    store.record_evidence_batch(
        [
            ExecutionEvidence(
                id="node", run_id=run_id, node_id="echo", kind="node", status="running"
            ),
            ExecutionEvidence(
                id="agent",
                run_id=run_id,
                parent_id="node",
                node_id="echo",
                kind="agent",
                status="running",
            ),
            ExecutionEvidence(
                id="tool",
                run_id=run_id,
                parent_id="agent",
                node_id="echo",
                kind="tool",
                tool_id="example/echo/copy",
                status="failed",
            ),
            ExecutionEvidence(
                id="attempt",
                run_id=run_id,
                parent_id="tool",
                node_id="echo",
                kind="attempt",
                tool_id="example/echo/copy",
                status="failed",
                finished_at=datetime.now(UTC),
                error_code="transport_unavailable",
            ),
        ]
    )
    prepared = client.post(
        "/api/workflow-packages/api-package/prepare",
        json={
            "workflowKey": "main",
            "parameters": {"text": "test"},
        },
    ).json()
    assert prepared["ready"] is True
    plugin = next(item for item in prepared["requirements"] if item["kind"] == "plugin")
    assert plugin["observation"] == "failed" and plugin["observedAt"]
    assert plugin["observationError"] == "transport_unavailable"

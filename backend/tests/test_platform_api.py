from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.platform_dependencies import get_artifacts, get_launch_service, get_platform_store
from app.application.definitions import canonical_source, save_definition
from app.application.launch import LaunchService
from app.application.package_import import import_source
from app.domain.execution import ApplicationError, ExecutionEvidence
from app.domain.tool_contracts import PluginRelease, ToolDefinition, tool_contract_digest
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.package_seeds import load_seed_packages, seed_packages
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_services import FrozenSecretResolver
from app.main import create_app


class FixedCore:
    def current_digest(self) -> str:
        return "sha256:" + "a" * 64


def source(key: str = "api-package", *, model: bool = False) -> str:
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    strategy = (
        {"kind": "model", "modelRef": "local-model", "prompt": "Return JSON with text"}
        if model
        else {"kind": "deterministic", "toolId": "example/echo/copy"}
    )
    return json.dumps(
        {
            "apiVersion": "signaldeck.workflowPackage/v2",
            "metadata": {"key": key, "name": "API Package", "description": "Contract test"},
            "agents": {
                "echo": {
                    "inputSchema": schema,
                    "outputSchema": schema,
                    "strategy": strategy,
                    "tools": ["example/echo/copy"],
                }
            },
            "workflows": {
                "main": {
                    "inputSchema": schema,
                    "outputSchema": schema,
                    "nodes": {"echo": {"uses": "echo", "inputMapping": {"ref": "workflow.input"}}},
                    "outputMapping": {"ref": "nodes.echo.output"},
                }
            },
        }
    )


def release() -> dict[str, Any]:
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    tool = ToolDefinition(
        tool_id="example/echo/copy",
        owner_plugin_id="example/echo",
        input_schema=schema,
        output_schema=schema,
    )
    return PluginRelease(
        plugin_id="example/echo",
        release_id="1.0.0",
        artifact_digest="sha256:" + "b" * 64,
        endpoint="http://127.0.0.1:1/mcp",
        tools=(tool,),
        contract_digest=tool_contract_digest((tool,)),
    ).model_dump(mode="json", by_alias=True)


def platform_environment(
    session_factory: sessionmaker[Session], tmp_path: Path, *, inline_threshold: int
) -> Iterator[tuple[TestClient, PlatformStore, ArtifactStore]]:
    artifacts = ArtifactStore(tmp_path / "artifacts", inline_threshold=inline_threshold)
    store = PlatformStore(session_factory, artifacts)
    store.initialize()
    app = create_app(init_database=False)
    app.dependency_overrides[get_platform_store] = lambda: store
    app.dependency_overrides[get_launch_service] = lambda: LaunchService(store, FixedCore())
    app.dependency_overrides[get_artifacts] = lambda: artifacts
    with TestClient(app) as client:
        yield client, store, artifacts


@pytest.fixture
def platform(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> Iterator[tuple[TestClient, PlatformStore, ArtifactStore]]:
    yield from platform_environment(session_factory, tmp_path, inline_threshold=64)


def test_definition_editor_uses_canonical_immutable_source(platform: tuple) -> None:
    client, _, _ = platform
    validated = client.post(
        "/api/workflow-packages/validate-manifest", json={"manifestSource": source()}
    )
    assert validated.status_code == 200
    assert validated.json()["diagnostics"] == []
    created = client.post("/api/workflow-packages", json={"manifestSource": source()})
    assert created.status_code == 201
    document = created.json()
    assert document["packageHash"] == validated.json()["contentHash"]
    assert document["plans"]["main"]["nodeOrder"] == ["echo"]
    again = client.patch(
        "/api/workflow-packages/api-package",
        json={"manifestSource": "# layout change\n" + document["source"]},
    )
    assert again.status_code == 200
    assert again.json()["source"] == document["source"]
    assert again.json()["packageHash"] == document["packageHash"]
    renamed = client.patch(
        "/api/workflow-packages/api-package", json={"manifestSource": source("different")}
    )
    assert renamed.status_code == 400
    assert renamed.json()["code"] == "package_key_conflict"


def test_invalid_editor_source_has_located_diagnostics(platform: tuple) -> None:
    client, _, _ = platform
    invalid = json.loads(source())
    invalid["workflows"]["main"]["nodes"]["echo"]["inputMapping"] = {"ref": "nodes.absent.output"}
    result = client.post(
        "/api/workflow-packages/validate-manifest",
        json={"manifestSource": json.dumps(invalid, indent=2)},
    )
    assert result.status_code == 200
    assert result.json()["definition"] is None
    diagnostic = result.json()["diagnostics"][0]
    assert diagnostic["code"] == "unknown_reference"
    assert diagnostic["line"] is not None


def test_valid_array_workflow_input_can_be_launched_without_object_wrapping(
    platform: tuple,
) -> None:
    client, _, _ = platform
    value = json.loads(source())
    shape = {"type": "array", "items": {"type": "string"}, "minItems": 1}
    value["agents"]["echo"].update(
        {
            "inputSchema": shape,
            "outputSchema": shape,
            "strategy": {"kind": "model", "modelRef": "array-model", "prompt": "Return the input"},
            "tools": [],
        }
    )
    value["workflows"]["main"].update({"inputSchema": shape, "outputSchema": shape})
    assert (
        client.post(
            "/api/resources",
            json={
                "resourceId": "array-model",
                "kind": "model",
                "config": {"baseUrl": "http://127.0.0.1:9999/v1", "modelId": "fake"},
            },
        ).status_code
        == 200
    )
    validation = client.post(
        "/api/workflow-packages/validate-manifest", json={"manifestSource": json.dumps(value)}
    )
    assert validation.json()["diagnostics"] == []
    client.post("/api/workflow-packages", json={"manifestSource": json.dumps(value)})
    result = client.post(
        "/api/workflow-packages/api-package/launches",
        json={"workflowKey": "main", "parameters": ["one", "two"]},
    )
    assert result.status_code == 201
    assert client.get("/api/runs/" + result.json()["id"]).json()["spec"]["parameters"] == [
        "one",
        "two",
    ]
    invalid = client.post(
        "/api/workflow-packages/api-package/launches",
        json={"workflowKey": "main", "parameters": []},
    )
    assert invalid.status_code == 422


def test_launch_is_offline_atomic_and_retry_survives_disabled_plugin(platform: tuple) -> None:
    client, store, _ = platform
    assert (
        client.post("/api/plugins", json={"release": release(), "enabled": True}).status_code == 200
    )
    assert (
        client.post("/api/workflow-packages", json={"manifestSource": source()}).status_code == 201
    )
    body = {"workflowKey": "main", "parameters": {"text": "first"}, "launchId": "same-request"}
    launched = client.post("/api/workflow-packages/api-package/launches", json=body)
    assert launched.status_code == 201
    run_id = launched.json()["id"]
    assert launched.json()["status"] == "queued"
    assert len(store.pending_commands()) == 1
    assert store.get_run(run_id).spec.plugin_releases[0]["artifactDigest"] == "sha256:" + "b" * 64
    assert client.patch("/api/plugins/example/echo", json={"enabled": False}).status_code == 200
    retried = client.post("/api/workflow-packages/api-package/launches", json=body)
    assert retried.status_code == 201
    assert retried.json()["id"] == run_id
    assert len(store.pending_commands()) == 1
    conflict = client.post(
        "/api/workflow-packages/api-package/launches",
        json={**body, "parameters": {"text": "changed"}},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "launch_identity_conflict"
    assert client.get(f"/api/runs/{run_id}").status_code == 200
    cancelled = client.post(f"/api/runs/{run_id}/cancel")
    assert cancelled.json()["status"] == "queued"
    assert cancelled.json()["cancelRequestedAt"] is not None
    assert {item.kind for item in store.pending_commands()} == {"start", "cancel"}


def test_credentials_only_write_and_not_in_snapshots_or_validation_errors(platform: tuple) -> None:
    client, _, _ = platform
    credential = "private-test-value-318742"
    config = {"name": "Local", "baseUrl": "http://127.0.0.1:9999/v1", "modelId": "fake"}
    saved = client.post(
        "/api/resources",
        json={
            "resourceId": "local-model",
            "kind": "model",
            "config": config,
            "credentials": {"apiKey": credential},
        },
    )
    assert saved.status_code == 200
    assert saved.json()["hasCredentials"] is True
    assert credential not in saved.text
    assert credential not in client.get("/api/resources").text
    bad = client.post(
        "/api/resources",
        json={
            "resourceId": "bad",
            "kind": "tool",
            "config": {"pluginId": "example/echo", "scope": {"apiKey": credential}},
        },
    )
    assert bad.status_code == 422
    assert credential not in bad.text
    assert client.post("/api/plugins", json={"release": release()}).status_code == 200
    client.post("/api/workflow-packages", json={"manifestSource": source(model=True)})
    launched = client.post(
        "/api/workflow-packages/api-package/launches",
        json={"workflowKey": "main", "parameters": {"text": "hello"}},
    )
    assert launched.status_code == 201
    detail = client.get("/api/runs/" + launched.json()["id"])
    assert detail.json()["spec"]["modelBindings"]["local-model"]["modelId"] == "fake"
    assert credential not in detail.text


def test_artifact_download_verifies_content_and_uses_attachment(platform: tuple) -> None:
    client, _, artifacts = platform
    ref = artifacts.put(b"large result " * 50, "text/plain")
    result = client.get("/api/artifacts/" + ref.digest)
    assert result.status_code == 200
    assert result.content == b"large result " * 50
    assert result.headers["content-disposition"].startswith("attachment;")
    assert client.get("/api/artifacts/sha256:invalid").status_code == 404


def test_bound_credential_rotation_is_checked_atomically_before_io(platform: tuple) -> None:
    _, store, _ = platform
    config = {"pluginId": "example/echo", "scope": {}}
    first = store.save_resource(
        "echo-data", "tool", config, {"Authorization": "Bearer first-test-key"}
    )
    bindings = {
        "resourceBindings": {
            "echo-data": {**config, "credentialRevision": first["credentialRevision"]}
        }
    }
    resolver = FrozenSecretResolver(store.resolve_bound_credentials, bindings)
    assert asyncio.run(resolver.resolve("example/echo", ("echo-data",))) == {
        "Authorization": "Bearer first-test-key"
    }
    second = store.save_resource(
        "echo-data", "tool", config, {"Authorization": "Bearer second-test-key"}
    )
    assert second["credentialRevision"] != first["credentialRevision"]
    with pytest.raises(ApplicationError) as failure:
        asyncio.run(resolver.resolve("example/echo", ("echo-data",)))
    assert failure.value.code == "resource_binding_changed"
    assert "test-key" not in str(failure.value)
    assert store.resolve_bound_credentials("echo-data", second["credentialRevision"]) == {
        "Authorization": "Bearer second-test-key"
    }


def test_plugin_health_is_a_saved_release_specific_observation(platform: tuple) -> None:
    client, store, _ = platform
    descriptor = release()
    client.post("/api/plugins", json={"release": descriptor})
    client.post("/api/workflow-packages", json={"manifestSource": source()})
    run_id = client.post(
        "/api/workflow-packages/api-package/launches",
        json={"workflowKey": "main", "parameters": {"text": "hello"}},
    ).json()["id"]
    assert client.get("/api/plugins").json()["items"][0]["health"]["status"] == "not_observed"
    now = datetime.now(UTC)
    for identity, kind, parent in (
        ("node", "node", None),
        ("agent", "agent", "node"),
        ("operation", "tool", "agent"),
        ("network", "attempt", "operation"),
    ):
        store.record_evidence(
            ExecutionEvidence(
                id=identity,
                run_id=run_id,
                parent_id=parent,
                node_id="echo",
                kind=kind,
                status="succeeded",
                tool_id="example/echo/copy" if kind in {"tool", "attempt"} else None,
                operation_id="operation" if kind in {"tool", "attempt"} else None,
                finished_at=now,
            )
        )
    observed = client.get("/api/plugins").json()["items"][0]["health"]
    assert observed["status"] == "succeeded"
    assert observed["runId"] == run_id
    assert observed["evidenceId"] == "network"
    # The descriptor endpoint is deliberately offline; no network access was needed.
    upgraded = {**descriptor, "artifactDigest": "sha256:" + "c" * 64, "releaseId": "2.0.0"}
    client.post("/api/plugins", json={"release": upgraded})
    assert client.get("/api/plugins").json()["items"][0]["health"]["status"] == "not_observed"


def test_external_directory_import_is_optional_atomic_and_preserves_edits(platform, tmp_path):
    _, store, _ = platform
    assert load_seed_packages() == ()
    assert seed_packages(store) == seed_packages(store, tmp_path / "absent") == []
    directory = tmp_path / "external-packages"
    directory.mkdir()
    manifest = source("external-package")
    (directory / "broken.yaml").write_text("not: [valid")
    (directory / "valid.yml").write_text(manifest)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: seed_packages(store, directory), range(2)))
    assert all(items[0]["status"] == "error" for items in results)
    assert sorted(items[1]["status"] for items in results) == ["created", "preserved"]
    initial = store.get_package("external-package")
    assert save_definition(store, initial["source"]) == initial
    definition = json.loads(manifest)
    definition["metadata"]["description"] = "Operator-owned revision"
    updated = save_definition(store, canonical_source(definition))
    assert updated["packageHash"] != initial["packageHash"]
    assert seed_packages(store, directory)[1]["status"] == "preserved"
    assert store.get_package("external-package") == updated
    assert store.get_package("external-package", initial["packageHash"]) == initial


def test_external_directory_compiles_without_contacting_plugins(tmp_path, monkeypatch):
    import socket
    import sys

    from app.domain.definition_parser import parse_package_source

    def forbidden(*args, **kwargs):
        raise AssertionError("Package loading cannot contact external services")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    manifest = source("uninstalled-package")
    (tmp_path / "package.yaml").write_text(manifest)
    before = set(sys.modules)
    loaded = load_seed_packages(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].source == manifest
    assert loaded[0].compiled == parse_package_source(manifest)
    assert not any(
        name.startswith(("finance_plugin", "oracle_plugin", "notes_plugin"))
        for name in set(sys.modules) - before
    )


def test_import_api_uses_ordinary_revisions_and_requires_explicit_update(platform):
    client, store, _ = platform
    response = client.post(
        "/api/workflow-packages/import",
        json={"sources": [{"manifestSource": "no: ["}, {"manifestSource": source()}]},
    )
    assert response.status_code == 200
    assert [item["status"] for item in response.json()["items"]] == ["error", "created"]
    initial = store.get_package("api-package")
    assert save_definition(store, source()) == initial
    changed = json.loads(source())
    changed["metadata"]["description"] = "New external revision"
    payload = {"sources": [{"manifestSource": canonical_source(changed)}]}
    assert (
        client.post("/api/workflow-packages/import", json=payload).json()["items"][0]["status"]
        == "preserved"
    )
    assert store.get_package("api-package") == initial
    payload["mode"] = "update"
    assert (
        client.post("/api/workflow-packages/import", json=payload).json()["items"][0]["status"]
        == "updated"
    )
    assert store.get_package("api-package")["packageHash"] != initial["packageHash"]
    assert store.get_package("api-package", initial["packageHash"]) == initial


def test_missing_only_import_and_operator_save_share_atomic_identity_lock(platform):
    _, store, _ = platform
    definition = json.loads(source())
    definition["metadata"]["description"] = "Concurrent operator revision"
    with ThreadPoolExecutor(max_workers=2) as pool:
        imported = pool.submit(import_source, store, source(), missing_only=True)
        saved = pool.submit(save_definition, store, canonical_source(definition))
        assert imported.result()["status"] in {"created", "preserved"}
        operator = saved.result()
    assert store.get_package(operator["packageKey"]) == operator


@pytest.mark.parametrize("invalid_data", [False, True])
def test_api_starts_with_empty_or_invalid_external_directory(
    platform, tmp_path, monkeypatch, invalid_data
):
    from types import SimpleNamespace

    from app import main

    _, store, _ = platform
    if invalid_data:
        (tmp_path / "invalid.yaml").write_text("invalid: [")
    settings = main.get_settings().model_copy(update={"workflow_data_dir": str(tmp_path)})
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_platform_store", lambda: store)
    monkeypatch.setattr(main, "get_schedule_store", lambda: store)
    monkeypatch.setattr(
        main, "get_core_artifacts", lambda: SimpleNamespace(current_digest=lambda: "fixed-core")
    )
    app = main.create_app()
    app.dependency_overrides[get_platform_store] = lambda: store
    with TestClient(app) as client:
        assert client.get("/api/workflow-packages").json() == {"items": []}
        assert (
            client.post("/api/workflow-packages", json={"manifestSource": source()}).status_code
            == 201
        )
    assert len(app.state.workflow_imports) == int(invalid_data)

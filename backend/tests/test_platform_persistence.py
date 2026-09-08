"""Real PostgreSQL regressions for atomic launch and immutable recovery evidence."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.core.config import reset_settings_cache
from app.domain.execution import ApplicationError, ExecutionEvidence, ResolvedRunSpec
from app.domain.tool_contracts import (
    ArtifactRef,
    ToolInvocationContext,
    ToolOperationRecord,
    ToolResult,
)
from app.infrastructure.artifact_store import ArtifactIntegrityError, ArtifactStore
from app.infrastructure.evidence_store import PostgresToolEvidenceStore
from app.infrastructure.platform_models import CommandRow, PlatformBase
from app.infrastructure.platform_store import PlatformStore


@pytest.fixture()
def store(database_url: str):
    engine = create_engine(database_url)
    result = PlatformStore(sessionmaker(engine, expire_on_commit=False))
    result.initialize()
    yield result
    engine.dispose()


def spec(run_id: str = "run-1") -> ResolvedRunSpec:
    return ResolvedRunSpec(
        run_id=run_id,
        package_key="research",
        workflow_key="main",
        package_hash="sha256:one",
        definition={"agents": {}},
        plan={"nodes": []},
        parameters={"topic": "test"},
        core_artifact="sha256:core",
        deadline=datetime.now(UTC) + timedelta(minutes=5),
    )


def prepare_tree(store: PlatformStore):
    store.create_run(spec(), "launch-1")
    store.record_evidence(
        ExecutionEvidence(id="node", run_id="run-1", node_id="n", kind="node", status="running")
    )
    store.record_evidence(
        ExecutionEvidence(
            id="agent",
            run_id="run-1",
            parent_id="node",
            node_id="n",
            kind="agent",
            status="running",
        )
    )


def test_metadata_is_core_owned(store: PlatformStore):
    assert all(name.startswith("platform_") for name in PlatformBase.metadata.tables)
    with store.session_factory() as session:
        tables = session.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        assert all(row[0].startswith("platform_") for row in tables)


def test_atomic_launch_rollback_and_redelivery(store: PlatformStore):
    def interrupt(*args):
        raise RuntimeError("controlled transaction interruption")

    event.listen(CommandRow, "before_insert", interrupt)
    try:
        with pytest.raises(RuntimeError):
            store.create_run(spec(), "launch-1")
    finally:
        event.remove(CommandRow, "before_insert", interrupt)
    assert store.list_runs() == []
    assert store.pending_commands() == []
    created = store.create_run(spec(), "launch-1")
    command = store.pending_commands()[0]
    store.note_command_attempt(command.id)
    assert store.pending_commands()[0].attempts == 1
    replay = store.create_run(
        spec("run-other").model_copy(update={"package_hash": "new"}), "launch-1"
    )
    assert replay == created
    assert len(store.pending_commands()) == 1
    store.acknowledge_command(command.id)
    store.acknowledge_command(command.id)
    assert store.pending_commands() == []
    with pytest.raises(ApplicationError, match="different input"):
        store.create_run(
            spec("run-other").model_copy(update={"parameters": {"topic": "changed"}}), "launch-1"
        )
    assert store.get_run_by_launch_id("launch-1").id == created.id


def test_concurrent_launch_has_one_identity(store: PlatformStore):
    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(
            workers.map(lambda i: store.create_run(spec(f"run-{i}"), "same-intent"), range(8))
        )
    assert len({result.id for result in results}) == 1
    assert len(store.list_runs()) == 1
    assert len(store.pending_commands()) == 1


def test_cancel_acceptance_is_not_actual_stop(store: PlatformStore):
    store.create_run(spec(), "launch-1")
    store.project_run("run-1", "running")
    result = store.request_cancel("run-1")
    assert result.status == "running"
    assert result.cancel_requested_at is not None
    assert result.finished_at is None
    store.request_cancel("run-1")
    assert [command.kind for command in store.pending_commands()].count("cancel") == 1
    store.project_run("run-1", "cancelled")
    assert store.get_run("run-1").finished_at is not None
    with pytest.raises(ApplicationError):
        store.project_run("run-1", "running")


def test_revision_and_success_outputs_are_immutable(store: PlatformStore):
    store.save_package("p", "v1", {"v": 1}, {"plan": 1}, "h1")
    store.save_package("p", "v2", {"v": 2}, {"plan": 2}, "h2")
    assert store.get_package("p")["source"] == "v2"
    assert store.get_package("p", "h1")["source"] == "v1"
    with pytest.raises(ApplicationError):
        store.save_package("p", "changed", {"v": 1}, {"plan": 1}, "h1")
    store.create_run(spec(), "launch-1")
    store.project_run("run-1", "succeeded", {"amount": "1.00"})
    store.project_run("run-1", "succeeded", {"amount": "1.00"})
    with pytest.raises(ApplicationError):
        store.project_run("run-1", "succeeded", {"amount": "2.00"})
    assert store.get_run("run-1").output == {"amount": "1.00"}


def test_read_projection_does_not_decrypt(store: PlatformStore, monkeypatch):
    secret = "controlled-test-secret"
    monkeypatch.setenv("AGENT_PLATFORM_ENCRYPTION_KEY", "test-key-one")
    reset_settings_cache()
    store.save_resource("model", "model", {"model": "example"}, {"apiKey": secret})
    assert store.resolve_credentials("model") == {"apiKey": secret}
    with store.session_factory() as session:
        raw = session.execute(
            text("SELECT credentials FROM platform_resources WHERE id='model'")
        ).scalar_one()
    assert raw["__encrypted__"] is True
    assert secret not in str(raw)
    monkeypatch.setenv("AGENT_PLATFORM_ENCRYPTION_KEY", "test-key-two")
    reset_settings_cache()
    assert store.get_resource("model")["hasCredentials"] is True
    assert len(store.list_resources()) == 1
    store.save_resource("model", "model", {"model": "updated"})
    with pytest.raises(ValueError, match="Invalid encrypted"):
        store.resolve_credentials("model")
    assert secret not in str(store.list_resources())


def test_plugin_release_reads_are_detached_and_immutable(store: PlatformStore):
    release = {"artifactDigest": "sha256:one", "endpoint": "http://unreachable.invalid/mcp"}
    store.install_plugin("test/plugin", release, enabled=False)
    release["endpoint"] = "changed"
    assert store.list_plugins()[0]["release"]["endpoint"] != "changed"
    with pytest.raises(ApplicationError):
        store.install_plugin("test/plugin", release)
    store.install_plugin("test/plugin", {"artifactDigest": "sha256:two"}, enabled=True)
    assert store.get_plugin_release("test/plugin", "sha256:one") is not None


def test_evidence_identity_and_parent_constraints(store: PlatformStore):
    prepare_tree(store)
    evidence = ExecutionEvidence(
        id="result",
        run_id="run-1",
        parent_id="agent",
        node_id="n",
        kind="model",
        status="succeeded",
        input={"prompt": "test"},
        output={"ok": True},
    )
    store.record_evidence(evidence)
    store.record_evidence(evidence)
    with pytest.raises(ApplicationError):
        store.record_evidence(evidence.model_copy(update={"output": {"ok": False}}))
    with pytest.raises(ApplicationError):
        store.record_evidence(evidence.model_copy(update={"input": {"prompt": "other"}}))
    with pytest.raises(ApplicationError):
        store.record_evidence(evidence.model_copy(update={"id": "new", "parent_id": "missing"}))
    with pytest.raises(ApplicationError):
        store.record_evidence(evidence.model_copy(update={"id": "cross-node", "node_id": "other"}))
    with pytest.raises(ApplicationError):
        store.record_evidence(evidence.model_copy(update={"id": "no-agent", "parent_id": "node"}))


def test_durable_tool_attempt_tree_and_recovery(store: PlatformStore):
    prepare_tree(store)
    context = ToolInvocationContext(
        run_id="run-1",
        node_id="n",
        invocation_id="agent",
        operation_id="op",
        deadline=datetime.now(UTC) + timedelta(minutes=5),
        tool_grants=("x/y/z",),
    )
    operation = ToolOperationRecord(
        context=context,
        tool_id="x/y/z",
        input_digest="sha256:test",
        arguments={"query": "visible input"},
    )

    async def scenario():
        gateway_store = PostgresToolEvidenceStore(store.session_factory)
        reserved = await asyncio.gather(
            *(gateway_store.reserve_operation(operation) for _ in range(8))
        )
        assert reserved.count(True) == 1
        attempts = await asyncio.gather(
            *(gateway_store.begin_attempt("op", "execute") for _ in range(8))
        )
        assert sorted(attempts) == list(range(1, 9))
        restarted = PostgresToolEvidenceStore(store.session_factory)
        pending = await restarted.get_operation("op")
        assert pending.status == "unknown" and pending.attempts == 8
        unknown = ToolResult(status="unknown", code="response_lost")
        await restarted.finish_attempt("op", 1, unknown)
        await restarted.finish_operation("op", unknown)
        query_attempt = await restarted.begin_attempt("op", "query")
        success = ToolResult(status="succeeded", output={"saved": True})
        await restarted.finish_attempt("op", query_attempt, success)
        assert (
            await PostgresToolEvidenceStore(store.session_factory).get_operation("op")
        ).result == success
        await restarted.finish_operation("op", success)
        await restarted.finish_operation("op", success)
        with pytest.raises(ApplicationError):
            await restarted.finish_operation("op", unknown)
        with pytest.raises(ApplicationError):
            await restarted.begin_attempt("op", "execute")
        return await restarted.get_operation("op")

    result = asyncio.run(scenario())
    assert result.status == "succeeded" and result.attempts == 9
    detail = store.get_run("run-1")
    operation_evidence = next(item for item in detail.evidence if item.id == "op")
    assert operation_evidence.parent_id == "agent"
    assert operation_evidence.input == {"query": "visible input"}
    attempts = [item for item in detail.evidence if item.kind == "attempt"]
    assert len(attempts) == 9 and all(item.parent_id == "op" for item in attempts)
    assert next(item for item in attempts if item.attempt == 9).metadata["networkKind"] == "query"


def test_historical_run_retains_frozen_bindings(store: PlatformStore):
    frozen = spec().model_copy(
        update={
            "model_bindings": {"m": {"model": "original"}},
            "plugin_releases": [{"artifactDigest": "sha256:original"}],
            "resource_bindings": {"r": {"scope": "original"}},
        }
    )
    store.create_run(frozen, "launch-1")
    store.save_resource("m", "model", {"model": "replacement"})
    store.save_resource("r", "tool", {"scope": "replacement"})
    store.install_plugin("example/plugin", {"artifactDigest": "sha256:replacement"})
    before = store.get_run("run-1")
    assert before.spec == frozen
    before.spec.model_bindings["m"]["model"] = "mutated read"
    assert store.get_run("run-1").spec == frozen


def test_large_tool_evidence_cas_recovery(store: PlatformStore, tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts", inline_threshold=100)
    store.artifacts = artifacts
    prepare_tree(store)
    arguments = {"document": "large safe input " * 100}
    output = {"document": "large confirmed output " * 100}
    context = ToolInvocationContext(
        run_id="run-1",
        node_id="n",
        invocation_id="agent",
        operation_id="large-op",
        deadline=datetime.now(UTC) + timedelta(minutes=5),
        tool_grants=("x/y/z",),
    )
    operation = ToolOperationRecord(
        context=context, tool_id="x/y/z", input_digest="sha256:test", arguments=arguments
    )

    async def scenario():
        gateway_store = PostgresToolEvidenceStore(store.session_factory, artifacts)
        assert await gateway_store.reserve_operation(operation)
        attempt = await gateway_store.begin_attempt("large-op", "execute")
        success = ToolResult(status="succeeded", output=output)
        await gateway_store.finish_attempt("large-op", attempt, success)
        restarted = PostgresToolEvidenceStore(store.session_factory, artifacts)
        recovered = await restarted.get_operation("large-op")
        assert recovered.arguments == arguments
        assert recovered.result == success
        await restarted.finish_operation("large-op", success)
        with pytest.raises(ApplicationError):
            await restarted.finish_operation(
                "large-op", ToolResult(status="succeeded", output={"changed": True})
            )

    asyncio.run(scenario())
    evidence = store.get_evidence("large-op")
    assert set(evidence.input) == {"$artifact"}
    assert set(evidence.output) == {"$artifact"}
    assert artifacts.read_json(ArtifactRef.model_validate(evidence.input["$artifact"])) == arguments
    assert artifacts.read_json(ArtifactRef.model_validate(evidence.output["$artifact"])) == output
    attempt = store.get_evidence("large-op:attempt:1")
    assert attempt.input == evidence.input and attempt.output == evidence.output
    with store.session_factory() as session:
        raw = session.execute(
            text("SELECT payload FROM platform_tool_operations WHERE id='large-op'")
        ).scalar_one()
    assert raw["arguments"] == evidence.input
    assert raw["result"]["output"] == evidence.output
    assert "large confirmed output" not in str(raw)


def test_generic_evidence_cas_and_run_output_are_immutable(store: PlatformStore, tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts", inline_threshold=100)
    store.artifacts = artifacts
    prepare_tree(store)
    content = {"text": "large model evidence " * 100}
    evidence = ExecutionEvidence(
        id="model-cas",
        run_id="run-1",
        node_id="n",
        parent_id="agent",
        kind="model",
        status="succeeded",
        input=content,
        output=content,
    )
    store.record_evidence(evidence)
    persisted = store.get_evidence("model-cas")
    assert persisted.input == persisted.output
    assert set(persisted.output) == {"$artifact"}
    store.record_evidence(evidence)
    store.record_evidence(persisted)
    with pytest.raises(ApplicationError):
        store.record_evidence(evidence.model_copy(update={"output": {"changed": True}}))
    store.project_run("run-1", "succeeded", content)
    store.project_run("run-1", "succeeded", persisted.output)
    assert store.get_run("run-1").output == persisted.output
    with pytest.raises(ApplicationError):
        store.project_run("run-1", "succeeded", {"changed": True})
    # Historical metadata reads remain available when the artifact volume is absent.
    no_volume = PlatformStore(store.session_factory)
    assert no_volume.get_run("run-1").output == persisted.output
    assert no_volume.get_evidence("model-cas").input == persisted.input


def test_recovery_requires_the_exact_artifact(store: PlatformStore, tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts", inline_threshold=100)
    prepare_tree(store)
    operation = ToolOperationRecord(
        context=ToolInvocationContext(
            run_id="run-1",
            node_id="n",
            invocation_id="agent",
            operation_id="missing-cas",
            deadline=datetime.now(UTC) + timedelta(minutes=5),
            tool_grants=("x/y/z",),
        ),
        tool_id="x/y/z",
        input_digest="sha256:test",
        arguments={"document": "large input" * 100},
    )
    asyncio.run(
        PostgresToolEvidenceStore(store.session_factory, artifacts).reserve_operation(operation)
    )
    wrong_volume = ArtifactStore(tmp_path / "empty-volume", inline_threshold=100)
    with pytest.raises(ArtifactIntegrityError, match="unavailable"):
        asyncio.run(
            PostgresToolEvidenceStore(store.session_factory, wrong_volume).get_operation(
                "missing-cas"
            )
        )
    assert store.get_evidence("missing-cas").status == "pending"


def test_evidence_batch_confirms_model_and_attempt_atomically(store: PlatformStore):
    prepare_tree(store)
    model = ExecutionEvidence(
        id="batch-model",
        run_id="run-1",
        node_id="n",
        parent_id="agent",
        kind="model",
        status="running",
        input={"messages": []},
    )
    attempt = ExecutionEvidence(
        id="batch-attempt",
        run_id="run-1",
        node_id="n",
        parent_id="batch-model",
        kind="attempt",
        status="running",
        input={"messages": []},
    )
    store.record_evidence_batch([model, attempt])
    model_success = model.model_copy(
        update={"status": "succeeded", "output": {"answer": "confirmed"}}
    )
    attempt_success = attempt.model_copy(
        update={"status": "succeeded", "output": {"answer": "confirmed"}}
    )
    with pytest.raises(ApplicationError):
        store.record_evidence_batch(
            [model_success, attempt_success.model_copy(update={"node_id": "wrong"})]
        )
    assert store.get_evidence("batch-model").status == "running"
    assert store.get_evidence("batch-attempt").status == "running"
    store.record_evidence_batch([model_success, attempt_success])
    assert store.get_evidence("batch-model").status == "succeeded"
    assert store.get_evidence("batch-attempt").status == "succeeded"


def test_command_delivery_busy_guard_and_admission_rejection_are_atomic(store: PlatformStore):
    store.create_run(spec(), "launch-1")
    command = store.pending_commands()[0]
    with store.command_delivery(command.id) as acquired:
        assert acquired
        with store.command_delivery(command.id) as concurrent:
            assert not concurrent
        store.reject_run_admission(command.id, "core_artifact_unavailable")
    detail = store.get_run("run-1")
    assert detail.status == "failed" and detail.error_code == "core_artifact_unavailable"
    assert store.command_rejection(command.id) == "core_artifact_unavailable"
    store.reject_run_admission(command.id, "other_failure")
    assert store.command_rejection(command.id) == "core_artifact_unavailable"
    assert detail.output is None and detail.finished_at is not None
    assert store.pending_commands() == []
    with store.command_delivery(command.id) as delivered:
        assert not delivered


def test_admission_rejection_keeps_confirmed_run_output(store: PlatformStore):
    store.create_run(spec(), "launch-1")
    store.project_run("run-1", "succeeded", {"answer": "confirmed"})
    store.reject_run_admission("start:run-1", "core_artifact_unavailable")
    assert store.get_run("run-1").status == "succeeded"
    assert store.command_rejection("start:run-1") is None
    assert store.get_run("run-1").output == {"answer": "confirmed"}
    assert store.pending_commands() == []


def test_credential_revision_changes_only_on_explicit_secret_write(store: PlatformStore):
    first = store.save_resource("resource", "tool", {"scope": "one"}, {"apiKey": "first"})
    assert first["credentialRevision"]
    updated_config = store.save_resource("resource", "tool", {"scope": "two"})
    assert updated_config["credentialRevision"] == first["credentialRevision"]
    rotated = store.save_resource("resource", "tool", {"scope": "two"}, {"apiKey": "second"})
    assert rotated["credentialRevision"] != first["credentialRevision"]
    assert "second" not in str(rotated)
    assert store.list_resources("tool")[0]["credentialRevision"] == rotated["credentialRevision"]
    cleared = store.save_resource("resource", "tool", {"scope": "two"}, {})
    assert cleared["credentialRevision"] != rotated["credentialRevision"]
    assert not cleared["hasCredentials"]


def test_cache_provenance_persists_in_tool_and_network_evidence(store: PlatformStore):
    from app.domain.tool_contracts import ToolCacheProvenance

    prepare_tree(store)
    now = datetime.now(UTC)
    provenance = ToolCacheProvenance(
        hit=False,
        source_run_id="run-1",
        source_operation_id="cached-op",
        fetched_at=now,
        expires_at=now + timedelta(seconds=30),
        cache_key="sha256:" + "a" * 64,
    )
    operation = ToolOperationRecord(
        context=ToolInvocationContext(
            run_id="run-1",
            node_id="n",
            invocation_id="agent",
            operation_id="cached-op",
            deadline=now + timedelta(seconds=30),
            tool_grants=("x/y/z",),
        ),
        tool_id="x/y/z",
        input_digest="sha256:test",
        arguments={"value": 1},
    )

    async def scenario():
        evidence = PostgresToolEvidenceStore(store.session_factory)
        await evidence.reserve_operation(operation)
        attempt = await evidence.begin_attempt("cached-op", "execute")
        result = ToolResult(status="succeeded", output={"value": 2}, cache_provenance=provenance)
        await evidence.finish_attempt("cached-op", attempt, result)
        await evidence.finish_operation("cached-op", result)

    asyncio.run(scenario())
    expected = provenance.model_dump(mode="json", by_alias=True)
    assert store.get_evidence("cached-op").metadata["cacheProvenance"] == expected
    assert store.get_evidence("cached-op").metadata["inputDigest"] == "sha256:test"
    assert store.get_evidence("cached-op:attempt:1").metadata["cacheProvenance"] == expected

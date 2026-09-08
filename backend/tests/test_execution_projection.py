"""Engine facts repair stalled projections without acquiring scheduling authority."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from temporalio.client import WorkflowExecutionStatus
from temporalio.testing import WorkflowEnvironment

from app.application.execution_projection import EngineTerminalFact, ExecutionProjector
from app.domain.execution import ExecutionEvidence, ResolvedRunSpec
from app.domain.tool_contracts import ToolInvocationContext, ToolOperationRecord, ToolResult
from app.infrastructure.evidence_store import PostgresToolEvidenceStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_projection import TemporalExecutionObserver


@pytest.fixture()
def store(database_url):
    engine = create_engine(database_url)
    store = PlatformStore(sessionmaker(engine, expire_on_commit=False))
    store.initialize()
    yield store
    engine.dispose()


def create_run(store):
    run_id = str(uuid4())
    spec = ResolvedRunSpec(
        run_id=run_id,
        package_key="probe",
        workflow_key="main",
        package_hash="sha256:test",
        definition={},
        plan={},
        parameters={},
        core_artifact="sha256:test",
        deadline=datetime.now(UTC) + timedelta(seconds=1),
    )
    store.create_run(spec, run_id)
    return run_id


class Observer:
    def __init__(self, fact=None, error=None):
        self.fact, self.error = fact, error
        self.reads = []

    async def terminal_fact(self, run_id):
        self.reads.append(run_id)
        if self.error:
            raise self.error
        return self.fact


def test_observation_failure_or_running_never_infers_termination(store):
    run_id = create_run(store)
    for observer in [
        Observer(),
        Observer(error=TimeoutError()),
        Observer(error=OSError("private")),
    ]:
        result = asyncio.run(ExecutionProjector(store, observer).project_once())
        assert result["projected"] == 0
        assert store.get_run(run_id).status == "queued"
        assert store.get_run(run_id).finished_at is None
    assert len(store.pending_commands()) == 1


def test_worker_success_and_engine_projection_race_preserve_confirmed_output(store):
    run_id = create_run(store)
    fact = EngineTerminalFact(status="failed", finished_at=datetime.now(UTC), error_code="timeout")

    class RacingObserver(Observer):
        async def terminal_fact(self, identity):
            store.project_run(identity, "succeeded", {"answer": "confirmed"})
            return fact

    assert asyncio.run(ExecutionProjector(store, RacingObserver()).project_once())["projected"] == 0
    assert store.get_run(run_id).output == {"answer": "confirmed"}
    assert not store.project_engine_terminal(run_id, fact)


def test_engine_timeout_preserves_unknown_write_and_successful_sibling(store):
    run_id = create_run(store)
    store.record_evidence_batch(
        [
            ExecutionEvidence(id="node", run_id=run_id, node_id="n", kind="node", status="running"),
            ExecutionEvidence(
                id="agent",
                run_id=run_id,
                node_id="n",
                parent_id="node",
                kind="agent",
                status="running",
            ),
            ExecutionEvidence(
                id="sibling",
                run_id=run_id,
                node_id="s",
                kind="node",
                status="succeeded",
                output={"answer": 42},
            ),
        ]
    )

    async def reserve_write():
        evidence = PostgresToolEvidenceStore(store.session_factory)
        operation = ToolOperationRecord(
            context=ToolInvocationContext(
                run_id=run_id,
                node_id="n",
                invocation_id="agent",
                operation_id="write",
                deadline=datetime.now(UTC) + timedelta(seconds=30),
                tool_grants=("example/plugin/write",),
            ),
            tool_id="example/plugin/write",
            input_digest="sha256:one",
            arguments={"report": "once"},
        )
        await evidence.reserve_operation(operation)
        attempt = await evidence.begin_attempt("write", "execute")
        await evidence.finish_attempt(
            "write", attempt, ToolResult(status="unknown", code="response_lost")
        )
        await evidence.finish_operation("write", ToolResult(status="unknown", code="response_lost"))
        return evidence

    evidence = asyncio.run(reserve_write())
    original_attempt_finish = store.get_evidence("write:attempt:1").finished_at
    fact = EngineTerminalFact(
        status="failed",
        finished_at=datetime.now(UTC),
        error_code="engine_execution_timed_out",
        interrupted_status="timed_out",
    )
    assert asyncio.run(ExecutionProjector(store, Observer(fact)).project_once())["projected"] == 1
    detail = store.get_run(run_id)
    assert detail.status == "failed" and detail.output is None
    assert store.get_evidence("node").status == "timed_out"
    assert store.get_evidence("agent").status == "timed_out"
    assert store.get_evidence("sibling").output == {"answer": 42}
    assert store.get_evidence("write").status == "unknown"
    assert store.get_evidence("write").error_code == "response_lost"
    assert store.get_evidence("write:attempt:1").status == "unknown"
    assert store.get_evidence("write:attempt:1").finished_at == original_attempt_finish
    operation = asyncio.run(evidence.get_operation("write"))
    assert operation.status == "unknown" and operation.attempts == 1
    assert operation.result.code == "response_lost"
    assert not store.project_engine_terminal(run_id, fact)


def test_real_temporal_timeout_without_any_worker(store):
    async def scenario():
        async with await WorkflowEnvironment.start_local(
            dev_server_existing_path=os.environ.get("TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal")
        ) as environment:
            run_id = create_run(store)
            handle = await environment.client.start_workflow(
                "SignalDeckWorkflow",
                {},
                id=run_id,
                task_queue="no-worker-" + uuid4().hex,
                execution_timeout=timedelta(seconds=1),
            )
            projector = ExecutionProjector(store, TemporalExecutionObserver(environment.client))
            assert (await projector.project_once())["projected"] == 0
            deadline = asyncio.get_running_loop().time() + 10
            while (await handle.describe()).status != WorkflowExecutionStatus.TIMED_OUT:
                assert asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.05)
            assert (await projector.project_once())["projected"] == 1
            detail = store.get_run(run_id)
            assert detail.status == "failed"
            assert detail.error_code == "engine_execution_timed_out"
            assert detail.finished_at == (await handle.describe()).close_time
            assert detail.evidence == [] and detail.output is None
            assert (await projector.project_once())["examined"] == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "engine_status, expected_status, code",
    [
        (WorkflowExecutionStatus.CANCELED, "cancelled", "engine_execution_cancelled"),
        (WorkflowExecutionStatus.FAILED, "failed", "engine_execution_failed"),
        (WorkflowExecutionStatus.TERMINATED, "failed", "engine_execution_terminated"),
        (WorkflowExecutionStatus.COMPLETED, "succeeded", None),
    ],
)
def test_temporal_terminal_mapping_uses_only_observed_facts(engine_status, expected_status, code):
    from types import SimpleNamespace

    finished = datetime.now(UTC)

    class Handle:
        async def describe(self, **kwargs):
            return SimpleNamespace(status=engine_status, close_time=finished)

        async def result(self, **kwargs):
            assert engine_status == WorkflowExecutionStatus.COMPLETED
            return {"status": "succeeded", "output": {"answer": "confirmed"}, "errorCode": None}

    class Client:
        def get_workflow_handle(self, run_id):
            return Handle()

    fact = asyncio.run(TemporalExecutionObserver(Client()).terminal_fact("run"))
    assert fact.status == expected_status and fact.error_code == code
    assert fact.finished_at == finished
    assert fact.output == ({"answer": "confirmed"} if expected_status == "succeeded" else None)

"""Late cancellation must not abandon terminal evidence already being committed."""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import activity, workflow
from temporalio.api.enums.v1 import EventType
from temporalio.testing import WorkflowEnvironment

from app.application.execution_projection import ExecutionProjector
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_activities import RuntimeActivities
from app.infrastructure.temporal_agent import AgentWorkflow
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_projection import TemporalExecutionObserver
from app.infrastructure.temporal_services import TemporalServices
from app.infrastructure.temporal_workflows import SignalDeckWorkflow
from app.workers import durable_worker
from tests.test_durable_runtime_support import CORE, make_spec, tool_server


@workflow.defn(name="AgentWorkflow", sandboxed=False)
class ObservedAgentWorkflow(AgentWorkflow):
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await super().run(payload)

    @workflow.query
    def cancellation_received(self) -> bool:
        return workflow.cancellation_reason() is not None


@workflow.defn(name="SignalDeckWorkflow", sandboxed=False)
class ObservedSignalDeckWorkflow(SignalDeckWorkflow):
    @workflow.run
    async def run(self, spec: dict[str, Any]) -> dict[str, Any]:
        return await super().run(spec)

    @workflow.query
    def cancellation_received(self) -> bool:
        return workflow.cancellation_reason() is not None


@pytest.mark.parametrize("kind", ["agent", "node"])
def test_cancel_during_terminal_projection_preserves_completed_evidence(
    session_factory, tmp_path, monkeypatch, kind
):
    async def scenario():
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(session_factory, artifacts=artifacts)
        store.initialize()
        entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        method_name = "project_" + kind
        original = getattr(RuntimeActivities, method_name)
        diagnostics = Path(os.environ.get("SIGNALDECK_CANCEL_DIAGNOSTICS", str(tmp_path))) / kind
        diagnostics.mkdir(parents=True, exist_ok=True)

        @activity.defn(name=method_name)
        async def held_projection(self, payload: dict[str, Any]) -> None:
            if payload["status"] == "succeeded":
                entered.set()
                try:
                    while not release.is_set():
                        activity.heartbeat()
                        try:
                            await asyncio.wait_for(release.wait(), 0.05)
                        except TimeoutError:
                            pass
                except asyncio.CancelledError:
                    cancelled.set()
                    raise
            await original(self, payload)

        monkeypatch.setattr(RuntimeActivities, method_name, held_projection)
        monkeypatch.setattr(durable_worker, "AgentWorkflow", ObservedAgentWorkflow)
        monkeypatch.setattr(durable_worker, "SignalDeckWorkflow", ObservedSignalDeckWorkflow)
        monkeypatch.setattr(
            durable_worker,
            "Worker",
            partial(
                durable_worker.Worker,
                default_heartbeat_throttle_interval=timedelta(milliseconds=50),
                max_heartbeat_throttle_interval=timedelta(milliseconds=100),
            ),
        )
        events = []
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=os.environ.get(
                    "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                ),
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            tool_server(events) as transport,
        ):
            services = TemporalServices(
                store, artifacts, lambda bindings: transport, CORE, lambda: None
            )
            async with await durable_worker.create_worker(
                environment.client, services, "terminal-projection"
            ):
                spec = make_spec(deadline=60)
                store.create_run(spec, spec.run_id)
                handle = await environment.client.start_workflow(
                    "SignalDeckWorkflow",
                    spec.model_dump(mode="json", by_alias=True),
                    id=spec.run_id,
                    task_queue="terminal-projection",
                )
                owner = (
                    environment.client.get_workflow_handle(spec.run_id + ":a:agent:1")
                    if kind == "agent"
                    else handle
                )
                try:
                    await asyncio.wait_for(entered.wait(), 15)
                    await handle.cancel()
                    async with asyncio.timeout(5):
                        while not await owner.query(
                            "cancellation_received", rpc_timeout=timedelta(seconds=2)
                        ):
                            await asyncio.sleep(0.01)
                    history = await owner.fetch_history(rpc_timeout=timedelta(seconds=3))
                    terminal_id = max(
                        event.event_id
                        for event in history.events
                        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
                        and event.activity_task_scheduled_event_attributes.activity_type.name
                        == method_name
                    )
                    interrupted = any(
                        event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_CANCEL_REQUESTED
                        and event.activity_task_cancel_requested_event_attributes.scheduled_event_id
                        == terminal_id
                        for event in history.events
                    )
                    if interrupted:
                        # Observe an actual pre-commit cancellation before releasing the gate.
                        await asyncio.wait_for(cancelled.wait(), 5)
                    release.set()
                    result = await asyncio.wait_for(handle.result(), 8)
                    assert result["status"] == "cancelled"
                    await ExecutionProjector(
                        store, TemporalExecutionObserver(environment.client)
                    ).project_once()
                    detail = store.get_run(spec.run_id)
                    assert detail is not None
                    (diagnostics / "run.json").write_text(detail.model_dump_json(by_alias=True))
                    history = await owner.fetch_history(rpc_timeout=timedelta(seconds=3))
                    (diagnostics / "history.json").write_text(history.to_json())
                    assert not interrupted
                    assert not cancelled.is_set()
                    assert all(item.status != "running" for item in detail.evidence), detail
                    completed = [item for item in detail.evidence if item.kind == kind]
                    assert len(completed) == 1 and completed[0].status == "succeeded"
                    assert completed[0].finished_at is not None
                    assert [event[0] for event in events] == ["start", "end"]
                finally:
                    release.set()

    asyncio.run(scenario())

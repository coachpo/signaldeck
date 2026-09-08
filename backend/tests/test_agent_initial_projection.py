"""Cancellation must finish an Agent whose initial projection already committed."""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from functools import partial
from typing import Any

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import activity
from temporalio.testing import WorkflowEnvironment

from app.application.execution_projection import ExecutionProjector
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_activities import RuntimeActivities
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_projection import TemporalExecutionObserver
from app.infrastructure.temporal_services import TemporalServices
from app.workers import durable_worker
from tests.test_durable_runtime_support import CORE, make_spec, tool_server


def test_parent_cancellation_after_initial_agent_projection_finishes_evidence(
    session_factory, tmp_path, monkeypatch
):
    async def scenario():
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(session_factory, artifacts=artifacts)
        store.initialize()
        recorded, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
        original_projection = RuntimeActivities.project_agent

        @activity.defn(name="project_agent")
        async def gated_projection(self, payload: dict[str, Any]) -> None:
            await original_projection(self, payload)
            if payload["status"] != "running":
                return
            # Hold only the reply: the real PostgreSQL projection has already committed.
            recorded.set()
            try:
                while not release.is_set():
                    activity.heartbeat()
                    try:
                        await asyncio.wait_for(release.wait(), timeout=0.05)
                    except TimeoutError:
                        pass
            except asyncio.CancelledError:
                cancelled.set()
                raise

        monkeypatch.setattr(RuntimeActivities, "project_agent", gated_projection)
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
                environment.client, services, "initial-agent-projection"
            ):
                spec = make_spec(deadline=60)
                store.create_run(spec, spec.run_id)
                handle = await environment.client.start_workflow(
                    "SignalDeckWorkflow",
                    spec.model_dump(mode="json", by_alias=True),
                    id=spec.run_id,
                    task_queue="initial-agent-projection",
                )
                try:
                    await asyncio.wait_for(recorded.wait(), timeout=15)
                    before = store.get_run(spec.run_id)
                    assert any(
                        item.kind == "agent" and item.status == "running"
                        for item in before.evidence
                    )
                    await handle.cancel()
                    result = await asyncio.wait_for(handle.result(), timeout=15)
                    assert result["status"] == "cancelled"
                    assert cancelled.is_set()
                    await ExecutionProjector(
                        store, TemporalExecutionObserver(environment.client)
                    ).project_once()
                    detail = store.get_run(spec.run_id)
                    assert detail.status == "cancelled"
                    assert not events
                    assert {item.kind for item in detail.evidence} == {"node", "agent"}
                    assert all(item.status == "cancelled" for item in detail.evidence), detail
                    assert all(item.finished_at is not None for item in detail.evidence)
                finally:
                    release.set()

    asyncio.run(scenario())

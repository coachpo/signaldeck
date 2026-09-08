"""Run the artifact-pinned Temporal worker selected by the core supervisor."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic_ai.durable_exec.temporal import AgentPlugin
from temporalio.client import Client
from temporalio.worker import Worker

from app.application.launch import LaunchService
from app.application.tool_gateway import ToolGateway
from app.core.config import get_settings
from app.core.telemetry import configure_logfire
from app.db.engine import get_session_factory
from app.domain.tool_contracts import PluginRelease, ToolCatalog, ToolInvocationContext, ToolResult
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.core_artifacts import CoreArtifactStore
from app.infrastructure.core_artifacts import task_queue as artifact_task_queue
from app.infrastructure.evidence_store import PostgresToolEvidenceStore
from app.infrastructure.mcp_transport import McpToolTransport
from app.infrastructure.model_runtime import GatewayModel
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.resource_limiter import PostgresResourceLimiter
from app.infrastructure.schedule_store import ScheduleStore
from app.infrastructure.temporal_activities import RuntimeActivities
from app.infrastructure.temporal_agent import AgentWorkflow, create_agent
from app.infrastructure.temporal_client import connect_client
from app.infrastructure.temporal_dispatch import TemporalRunEngine
from app.infrastructure.temporal_services import FrozenSecretResolver, TemporalServices
from app.infrastructure.temporal_workflows import SignalDeckWorkflow
from app.infrastructure.tool_cache_store import PostgresToolCacheStore
from app.workers.schedule_fire import ScheduleFireWorkflow, TemporalScheduleActivities


async def create_worker(
    client: Client,
    services: TemporalServices,
    task_queue: str,
    *,
    workflows: Sequence[type] = (),
    activities: Sequence[Any] = (),
) -> Worker:
    limiter = PostgresResourceLimiter(services.store.session_factory)
    await asyncio.to_thread(limiter.initialize)
    tool_evidence = PostgresToolEvidenceStore(services.store.session_factory, services.artifacts)
    cache = PostgresToolCacheStore(services.store.session_factory, services.artifacts)
    await asyncio.to_thread(cache.initialize)
    transport_factory = services.transport

    async def invoke(
        bindings: dict[str, Any],
        tool_id: str,
        arguments: dict[str, Any],
        context: ToolInvocationContext,
    ) -> ToolResult:
        catalog = ToolCatalog(
            tuple(PluginRelease.model_validate(item) for item in bindings["pluginReleases"])
        )
        gateway = ToolGateway(
            catalog, transport_factory(bindings), tool_evidence, limiter, cache=cache
        )
        while True:
            result = await gateway.call(tool_id, arguments, context)
            if result.code != "operation_in_progress":
                return result
            remaining = (context.deadline - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                return ToolResult(status="unknown", code="deadline_effect_unconfirmed")
            # A redelivered Activity waits for the live owner without spending another
            # logical operation or network attempt, and retains the original deadline.
            await asyncio.sleep(min(0.05, remaining))

    runtime = RuntimeActivities(
        services.store,
        services.artifacts,
        invoke,
        services.core_artifact,
        services.verify_core,
    )
    bound_agent = create_agent(
        GatewayModel(services.store, services.store.resolve_bound_credentials, services.artifacts),
        invoke,
    )
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[SignalDeckWorkflow, AgentWorkflow, *workflows],
        activities=[*runtime.registrations(), *activities],
        plugins=[AgentPlugin(bound_agent)],
        max_concurrent_activities=256,
    )


async def main() -> None:
    configure_logfire(service_name="signaldeck-worker")
    settings = get_settings()
    digest = os.environ["SIGNALDECK_CORE_ARTIFACT"]
    task_queue = os.environ["SIGNALDECK_TASK_QUEUE"]
    if task_queue != artifact_task_queue(digest):
        raise ValueError("Worker queue does not match its core artifact")
    core = CoreArtifactStore(Path(settings.core_artifact_dir))
    core.verify_worker(digest)
    artifacts = ArtifactStore(Path(settings.artifact_dir))
    store = PlatformStore(get_session_factory(), artifacts=artifacts)
    store.initialize()

    def verify_core() -> None:
        core.verify_worker(digest)

    services = TemporalServices(
        store=store,
        artifacts=artifacts,
        transport=lambda spec: McpToolTransport(
            FrozenSecretResolver(store.resolve_bound_credentials, spec)
        ),
        core_artifact=digest,
        verify_core=verify_core,
    )
    client = await connect_client(settings.temporal_address, artifacts)
    schedule_store = ScheduleStore(store.session_factory)
    schedule_store.initialize()
    schedule_activities = TemporalScheduleActivities(
        LaunchService(store, core), store, TemporalRunEngine(client, core), schedule_store
    )
    async with await create_worker(
        client,
        services,
        task_queue,
        workflows=[ScheduleFireWorkflow],
        activities=[schedule_activities.launch_fire, schedule_activities.wait_run],
    ):
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

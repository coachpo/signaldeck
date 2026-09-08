"""An Agent deadline stays a timeout when Temporal cancels a retried model activity."""

import asyncio
import os
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Request
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.responses import JSONResponse
from temporalio.testing import WorkflowEnvironment

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import TemporalServices
from app.workers.durable_worker import create_worker
from tests.test_durable_runtime_support import (
    CORE,
    make_spec,
    recompile_spec,
    serve_app,
    tool_server,
)


def test_retried_model_activity_uses_agent_deadline_not_cancellation(database_url, tmp_path):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "test-model-key"})
        retried = asyncio.Event()
        release = asyncio.Event()
        calls, events = [], []
        model_app = FastAPI()

        @model_app.post("/v1/chat/completions")
        async def completion(request: Request):
            await request.json()
            calls.append(datetime.now(UTC))
            if len(calls) >= 2:
                retried.set()
                await release.wait()
            return JSONResponse(
                status_code=503, content={"error": {"message": "controlled model failure"}}
            )

        try:
            async with (
                await WorkflowEnvironment.start_local(
                    dev_server_existing_path=os.environ.get(
                        "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                    ),
                    data_converter=create_data_converter(artifacts),
                    plugins=[PydanticAIPlugin()],
                ) as environment,
                tool_server(events) as transport,
                serve_app(model_app) as model_url,
            ):
                services = TemporalServices(
                    store, artifacts, lambda bindings: transport, CORE, lambda: None
                )
                async with await create_worker(environment.client, services, "agent-deadline"):
                    spec = make_spec(
                        kind="model", model_url=model_url + "/v1", model_store=store, deadline=30
                    )
                    spec.definition["agents"]["shared"]["budget"]["deadlineSeconds"] = 6
                    spec = recompile_spec(spec)
                    store.create_run(spec, spec.run_id)
                    handle = await environment.client.start_workflow(
                        "SignalDeckWorkflow",
                        spec.model_dump(mode="json", by_alias=True),
                        id=spec.run_id,
                        task_queue="agent-deadline",
                    )
                    try:
                        # The retry must be active, not merely scheduled near its retry limit.
                        await asyncio.wait_for(retried.wait(), 5)
                        result = await asyncio.wait_for(handle.result(), 12)
                        assert result["status"] == "failed"
                        assert not release.is_set()
                        detail = store.get_run(spec.run_id)
                        assert detail is not None
                        owners = [e for e in detail.evidence if e.kind in {"node", "agent"}]
                        assert len(owners) == 2
                        assert {e.status for e in owners} == {"timed_out"}, detail
                        assert all(e.error_code == "agent_deadline_exceeded" for e in owners)
                        attempts = sorted(
                            (e for e in detail.evidence if e.kind == "attempt"),
                            key=lambda e: e.attempt,
                        )
                        assert [e.attempt for e in attempts] == [1, 2]
                        assert attempts[0].metadata["httpStatus"] == 503
                        assert attempts[0].error_code == "model_http_error"
                        assert attempts[0].parent_id == attempts[1].parent_id
                        assert len(calls) == 2 and not events
                        agent = next(e for e in owners if e.kind == "agent")
                        assert agent.started_at is not None and agent.finished_at is not None
                        assert agent.finished_at >= agent.started_at + timedelta(seconds=6)
                        assert agent.finished_at < spec.deadline
                        assert all(e.status != "running" for e in detail.evidence)
                    finally:
                        release.set()
        finally:
            release.set()
            engine.dispose()

    asyncio.run(scenario())

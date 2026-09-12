"""A lost activity heartbeat must not confirm cancellation of a logical model call."""

import asyncio
import json
import os

import pytest
from fastapi import FastAPI, Request
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import activity
from temporalio.api.enums.v1 import TimeoutType
from temporalio.testing import WorkflowEnvironment

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.model_runtime import GatewayModel
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


@pytest.mark.parametrize("lose_heartbeat", [False, True], ids=["slow-healthy", "lost-heartbeat"])
def test_slow_model_heartbeat_liveness_and_recovery(
    session_factory, tmp_path, monkeypatch, lose_heartbeat
):
    heartbeat = activity.heartbeat
    request = GatewayModel.request
    request_io = GatewayModel._request_io
    cancellations = []
    request_started, interrupted = asyncio.Event(), asyncio.Event()
    release = asyncio.Event()
    beats = 0

    def drop_first_model_heartbeat(*details):
        nonlocal beats
        info = activity.info()
        if (
            info.activity_type.endswith("__model_request")
            and info.attempt == 1
            and request_started.is_set()
        ):
            beats += 1
            if lose_heartbeat and beats <= 2:
                return
            if not lose_heartbeat and beats == 3:
                release.set()
        heartbeat(*details)

    async def observe_cancellation(self, *args, **kwargs):
        try:
            return await request(self, *args, **kwargs)
        except asyncio.CancelledError:
            cancellations.append(activity.cancellation_details())
            interrupted.set()
            raise

    async def wait_for_interrupted_attempt(self, *args, **kwargs):
        if activity.info().attempt > 1:
            await interrupted.wait()
        return await request_io(self, *args, **kwargs)

    monkeypatch.setattr(activity, "heartbeat", drop_first_model_heartbeat)
    monkeypatch.setattr(GatewayModel, "request", observe_cancellation)
    monkeypatch.setattr(GatewayModel, "_request_io", wait_for_interrupted_attempt)

    async def scenario():
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(session_factory, artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "controlled-secret"})
        calls, events = [], []
        model_app = FastAPI()
        output = {"value": 1, "delay": 0, "tag": "recovered"}

        @model_app.post("/v1/chat/completions")
        async def completion(request: Request):
            calls.append(await request.json())
            if len(calls) == 1:
                request_started.set()
                await release.wait()
            return {
                "id": "controlled-response",
                "object": "chat.completion",
                "created": 0,
                "model": "controlled-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(output)},
                        "finish_reason": "stop",
                    }
                ],
            }

        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=os.environ.get(
                    "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                ),
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            tool_server(events) as transport,
            serve_app(model_app) as url,
        ):
            services = TemporalServices(
                store, artifacts, lambda bindings: transport, CORE, lambda: None
            )
            async with await create_worker(environment.client, services, "model-heartbeat"):
                spec = make_spec(kind="model", model_url=url + "/v1", model_store=store)
                spec.definition["agents"]["shared"]["tools"] = []
                spec = recompile_spec(spec)
                store.create_run(spec, spec.run_id)
                try:
                    result = await asyncio.wait_for(
                        environment.client.execute_workflow(
                            "SignalDeckWorkflow",
                            spec.model_dump(mode="json", by_alias=True),
                            id=spec.run_id,
                            task_queue="model-heartbeat",
                        ),
                        timeout=20,
                    )
                    detail = store.get_run(spec.run_id)
                    assert result["status"] == "succeeded", detail
                    assert result["output"] == output
                    models = [row for row in detail.evidence if row.kind == "model"]
                    attempts = sorted(
                        (row for row in detail.evidence if row.kind == "attempt"),
                        key=lambda row: row.attempt,
                    )
                    assert len(models) == 1 and models[0].status == "succeeded"
                    if lose_heartbeat:
                        assert len(cancellations) == 1
                        reason = cancellations[0]
                        assert reason.timed_out or reason.not_found
                        assert not reason.cancel_requested
                        history = await environment.client.get_workflow_handle(
                            f"{spec.run_id}:a:agent:1"
                        ).fetch_history()
                        retries = [
                            event.activity_task_started_event_attributes
                            for event in history.events
                            if event.activity_task_started_event_attributes.attempt == 2
                        ]
                        assert len(retries) == 1
                        assert (
                            retries[0].last_failure.timeout_failure_info.timeout_type
                            == TimeoutType.TIMEOUT_TYPE_HEARTBEAT
                        )
                        assert [row.attempt for row in attempts] == [1, 2]
                        assert attempts[0].status == "unknown"
                        assert attempts[0].error_code == "worker_interrupted"
                        assert attempts[0].output is None
                    else:
                        assert not cancellations
                        assert [row.attempt for row in attempts] == [1]
                        assert beats >= 3
                    assert attempts[-1].status == "succeeded"
                    assert all(row.parent_id == models[0].id for row in attempts)
                    assert all(row.status != "running" for row in detail.evidence)
                    assert len(calls) == len(attempts) and not events
                finally:
                    release.set()

    asyncio.run(scenario())

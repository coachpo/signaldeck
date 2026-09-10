"""Real local Temporal calls retain output limits, usage and replay identity."""

import asyncio
import os

from fastapi import FastAPI, Request
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from pydantic_ai.models import ModelRequestParameters
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment

from app.application.result_projection import project_result
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.model_runtime import GatewayModel
from app.infrastructure.model_usage import read_model_usage
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import TemporalServices
from app.workers.durable_worker import create_worker
from tests.test_durable_runtime_support import (
    CORE,
    make_spec,
    model_server,
    recompile_spec,
    serve_app,
    tool_server,
)


def test_temporal_output_limit_usage_replay_and_truncation(database_url, tmp_path):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "controlled-model-key"})
        calls, events, truncated_calls = [], [], []
        truncated = FastAPI()

        @truncated.post("/v1/chat/completions")
        async def truncate(request: Request):
            body = await request.json()
            truncated_calls.append(body)
            return {
                "id": "cut-off",
                "object": "chat.completion",
                "created": 0,
                "model": "probe",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"value":'},
                        "finish_reason": "length",
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
            }

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
                model_server(calls) as url,
                serve_app(truncated) as truncated_url,
            ):
                services = TemporalServices(
                    store, artifacts, lambda bindings: transport, CORE, lambda: None
                )
                async with await create_worker(environment.client, services, "usage-budget-test"):

                    async def execute(spec):
                        store.create_run(spec, spec.run_id)
                        return await environment.client.execute_workflow(
                            "SignalDeckWorkflow",
                            spec.model_dump(mode="json", by_alias=True),
                            id=spec.run_id,
                            task_queue="usage-budget-test",
                        )

                    spec = make_spec(kind="model", model_url=url, model_store=store)
                    spec.definition["agents"]["shared"]["budget"]["maxOutputTokens"] = 12
                    spec = recompile_spec(spec)
                    assert (await execute(spec))["status"] == "succeeded"
                    assert len(calls) == 2 and all(
                        call["max_completion_tokens"] == 12 for call in calls
                    )
                    before = read_model_usage(store, run_id=spec.run_id).summary
                    assert before.model_calls == 2 and before.network_attempts == 2
                    assert before.input_tokens == 16 and before.output_tokens == 16
                    assert before.usage_coverage == "complete"
                    detail = store.get_run(spec.run_id)
                    confirmed = next(
                        e for e in detail.evidence if e.kind == "model" and e.status == "succeeded"
                    )
                    gateway = GatewayModel(store, store.resolve_bound_credentials, artifacts)
                    await gateway.request(
                        [],
                        {"signaldeck_context": {"modelCallId": confirmed.id}},
                        ModelRequestParameters(),
                    )
                    assert len(calls) == 2
                    assert read_model_usage(store, run_id=spec.run_id).summary == before
                    cut = make_spec(
                        kind="model", model_url=truncated_url + "/v1", model_store=store
                    )
                    cut.definition["agents"]["shared"]["budget"].update(
                        {"maxOutputTokens": 1, "maxModelRequests": 2}
                    )
                    cut = recompile_spec(cut)
                    assert (await execute(cut))["status"] == "failed"
                    assert truncated_calls and all(
                        call["max_completion_tokens"] == 1 for call in truncated_calls
                    )
                    result = project_result(store.get_run(cut.run_id))
                    assert result.content_status == "not_available"
                    assert result.body is None
                    assert all(section.value != '{"value":' for section in result.sections)
                    cut_usage = read_model_usage(store, run_id=cut.run_id).summary
                    assert cut_usage.output_tokens == len(truncated_calls)
                    assert cut_usage.input_tokens == 8 * len(truncated_calls)
                    assert cut_usage.usage_coverage == "complete"
                    assert all(
                        evidence.metadata["finishReason"] == "length"
                        for evidence in store.get_run(cut.run_id).evidence
                        if evidence.kind == "model"
                    )
        finally:
            engine.dispose()

    asyncio.run(scenario())


def test_temporal_output_violation_stops_agent_retries_and_obeys_failure_policy(
    database_url, tmp_path
):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "controlled-model-key"})
        calls, events = [], []
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
                model_server(calls) as url,
            ):
                services = TemporalServices(
                    store, artifacts, lambda bindings: transport, CORE, lambda: None
                )
                async with await create_worker(
                    environment.client, services, "output-enforcement-test"
                ):
                    for policy in ("continue_independent", "fail_fast"):
                        spec = make_spec(kind="model", model_url=url, model_store=store)
                        spec.definition["agents"]["shared"]["budget"]["maxOutputTokens"] = 7
                        spec.definition["agents"]["safe"] = {
                            **spec.definition["agents"]["shared"],
                            "strategy": {"kind": "deterministic", "toolId": "example/probe/search"},
                        }
                        definition = spec.definition["workflows"]["main"]
                        definition["nodes"]["a"]["maxAttempts"] = 3
                        definition["nodes"]["b"] = {
                            **definition["nodes"]["a"],
                            "uses": "safe",
                            "maxAttempts": 1,
                        }
                        definition["maxParallelNodes"] = 1
                        definition["failurePolicy"] = policy
                        definition["outputMapping"] = {"ref": "nodes.b.output"}
                        spec = recompile_spec(spec)
                        store.create_run(spec, spec.run_id)
                        before_calls, before_events = len(calls), len(events)
                        result = await environment.client.execute_workflow(
                            "SignalDeckWorkflow",
                            spec.model_dump(mode="json", by_alias=True),
                            id=spec.run_id,
                            task_queue="output-enforcement-test",
                        )
                        assert result["status"] == "failed"
                        assert len(calls) == before_calls + 1
                        detail = store.get_run(spec.run_id)
                        model_calls = [e for e in detail.evidence if e.kind == "model"]
                        assert len(model_calls) == 1
                        assert model_calls[0].error_code == "model_output_limit_exceeded"
                        assert project_result(detail).error_category == "output_limit"
                        assert model_calls[0].metadata["usage"] == {
                            "inputTokens": 8,
                            "outputTokens": 8,
                        }
                        assert model_calls[0].metadata["finishReason"] == "tool_calls"
                        assert model_calls[0].output is None
                        assert not [
                            e for e in detail.evidence if e.node_id == "a" and e.kind == "tool"
                        ]
                        assert (
                            len(
                                [
                                    e
                                    for e in detail.evidence
                                    if e.node_id == "a" and e.kind == "agent"
                                ]
                            )
                            == 1
                        )
                        safe_node = next(
                            e for e in detail.evidence if e.node_id == "b" and e.kind == "node"
                        )
                        assert safe_node.status == (
                            "succeeded" if policy == "continue_independent" else "blocked"
                        )
                        assert len(events) - before_events == (
                            2 if policy == "continue_independent" else 0
                        )
                        usage = read_model_usage(store, run_id=spec.run_id).summary
                        assert usage.failed_calls == 1 and usage.network_attempts == 1
                        assert usage.input_tokens == 8 and usage.output_tokens == 8
                        assert usage.usage_coverage == "complete"
        finally:
            engine.dispose()

    asyncio.run(scenario())

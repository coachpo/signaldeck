"""Independent Agent limits and retry deadlines against actual Temporal model calls."""

import asyncio
import os

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment

from app.application.result_projection import project_result
from app.domain.definitions import Budget
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import TemporalServices
from app.workers.durable_worker import create_worker
from tests.test_durable_runtime_support import (
    CORE,
    make_spec,
    mapping,
    model_server,
    recompile_spec,
    tool_server,
)


def test_model_tool_budgets_are_invocation_local(database_url, tmp_path):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "test-model-key"})
        calls, events = [], []
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=os.environ.get(
                    "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                ),
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            tool_server(events) as transport,
            model_server(calls, tool_calls=2) as url,
        ):
            services = TemporalServices(
                store, artifacts, lambda bindings: transport, CORE, lambda: None
            )
            async with await create_worker(environment.client, services, "budget-test"):

                async def execute(spec):
                    store.create_run(spec, spec.run_id)
                    result = await environment.client.execute_workflow(
                        "SignalDeckWorkflow",
                        spec.model_dump(mode="json", by_alias=True),
                        id=spec.run_id,
                        task_queue="budget-test",
                    )
                    return result, store.get_run(spec.run_id)

                for key in ["maxToolCalls", "maxTokens"]:
                    spec = make_spec(kind="model", model_url=url, model_store=store)
                    spec.definition["agents"]["shared"]["budget"][key] = 1
                    before_tools, before_models = len(events), len(calls)
                    result, detail = await execute(recompile_spec(spec))
                    assert result["status"] == "failed"
                    assert len(calls) == before_models + 1
                    assert len(events) == before_tools
                    assert len([e for e in detail.evidence if e.kind == "model"]) == 1

                # Exact exhaustion stops before the next request, even when a
                # node permits fresh attempts; only the frozen override is used.
                for output_mode in ("auto", "provider_default"):
                    spec = make_spec(kind="model", model_url=url, model_store=store)
                    spec.definition["workflows"]["main"]["nodes"]["a"]["maxAttempts"] = 3
                    spec = recompile_spec(spec).model_copy(
                        update={
                            "effective_agent_budgets": {
                                "shared": Budget(max_tokens=16, max_output_tokens=output_mode)
                            }
                        }
                    )
                    before_models, before_tools = len(calls), len(events)
                    result, detail = await execute(spec)
                    assert result["status"] == "failed"
                    assert len(calls) == before_models + 1
                    assert len(events) == before_tools
                    assert not [e for e in detail.evidence if e.kind == "tool"]
                    assert project_result(detail).error_category == "budget_exceeded"
                    assert len([e for e in detail.evidence if e.kind == "agent"]) == 1
                    if output_mode == "auto":
                        assert calls[-1]["max_completion_tokens"] == 16
                    else:
                        assert "max_completion_tokens" not in calls[-1]

                for total_mode, output_mode in (
                    ("unlimited", "auto"),
                    ("unlimited", "provider_default"),
                    ("unlimited", 12),
                    (32, "provider_default"),
                ):
                    spec = make_spec(kind="model", model_url=url, model_store=store)
                    spec = spec.model_copy(
                        update={
                            "effective_agent_budgets": {
                                "shared": Budget(
                                    max_tokens=total_mode, max_output_tokens=output_mode
                                )
                            }
                        }
                    )
                    before_models = len(calls)
                    result, _ = await execute(spec)
                    assert result["status"] == "succeeded"
                    assert len(calls) == before_models + 2
                    for call in calls[before_models:]:
                        if isinstance(output_mode, int):
                            assert call["max_completion_tokens"] == output_mode
                        else:
                            assert "max_completion_tokens" not in call

                specs = []
                for tag in ["one", "two"]:
                    spec = make_spec(
                        {"a": {"uses": "shared", "inputMapping": mapping(tag, {"value": 7}, 0.5)}},
                        kind="model",
                        model_url=url,
                        model_store=store,
                    )
                    spec.definition["agents"]["shared"]["budget"]["maxParallelTools"] = 1
                    specs.append(recompile_spec(spec))
                results = await asyncio.gather(*(execute(spec) for spec in specs))
                for tag, (result, detail) in zip(["one", "two"], results, strict=True):
                    assert result["status"] == "succeeded"
                    assert result["output"]["tag"] == tag
                    observed = [event for event in events if event[1] == tag]
                    assert [event[0] for event in observed] == ["start", "end", "start", "end"]
                    assert len([e for e in detail.evidence if e.kind == "tool"]) == 2
                starts = {
                    tag: [at for kind, name, at in events if name == tag and kind == "start"]
                    for tag in ["one", "two"]
                }
                ends = {
                    tag: [at for kind, name, at in events if name == tag and kind == "end"]
                    for tag in ["one", "two"]
                }
                # Independent Run limits do not serialize both invocations behind one semaphore.
                assert max(starts["one"][0], starts["two"][0]) < min(ends["one"][0], ends["two"][0])
        engine.dispose()

    asyncio.run(scenario())


def test_model_network_retries_keep_original_deadline(database_url, tmp_path):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "test-model-key"})
        calls, events = [], []
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=os.environ.get(
                    "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                ),
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            tool_server(events) as transport,
            model_server(calls, fail_count=100) as url,
        ):
            services = TemporalServices(
                store, artifacts, lambda bindings: transport, CORE, lambda: None
            )
            async with await create_worker(environment.client, services, "retry-test"):
                spec = make_spec(kind="model", model_url=url, model_store=store, deadline=3)
                store.create_run(spec, spec.run_id)
                result = await asyncio.wait_for(
                    environment.client.execute_workflow(
                        "SignalDeckWorkflow",
                        spec.model_dump(mode="json", by_alias=True),
                        id=spec.run_id,
                        task_queue="retry-test",
                    ),
                    9,
                )
                assert result["status"] == "failed"
                assert 1 <= len(calls) <= 3
                detail = store.get_run(spec.run_id)
                attempts = [e for e in detail.evidence if e.kind == "attempt"]
                assert [e.attempt for e in attempts] == list(range(1, len(attempts) + 1))
                assert all(e.metadata.get("httpStatus") == 503 for e in attempts)
                assert all(e.error_code == "model_http_error" for e in attempts)
                assert not events
                assert any(e.kind == "node" and e.status == "timed_out" for e in detail.evidence)
        engine.dispose()

    asyncio.run(scenario())

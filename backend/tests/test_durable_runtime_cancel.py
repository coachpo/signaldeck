"""Cancellation traverses the real parent Workflow, Agent child and live I/O."""

import asyncio
import os

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import TemporalServices
from app.workers.durable_worker import create_worker
from tests.test_durable_runtime_support import CORE, make_spec, mapping, model_server, tool_server


def test_parent_cancellation_stops_active_model_and_tool(database_url, tmp_path):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "test-model-key"})
        events, calls, gate = [], [], asyncio.Event()
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=os.environ.get(
                    "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                ),
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            tool_server(events) as transport,
            model_server(calls, gate=gate) as url,
        ):
            services = TemporalServices(
                store, artifacts, lambda spec: transport, CORE, lambda: None
            )
            async with await create_worker(environment.client, services, "cancel-test"):
                for kind in ["model", "deterministic"]:
                    nodes = {
                        "a": {
                            "uses": "shared",
                            "inputMapping": mapping(
                                "A", {"value": 1}, 20 if kind == "deterministic" else 0
                            ),
                        },
                        "b": {
                            "uses": "shared",
                            "inputMapping": mapping("B", {"ref": "nodes.a.output.value"}),
                        },
                    }
                    spec = make_spec(nodes, kind=kind, model_url=url, model_store=store)
                    store.create_run(spec, spec.run_id)
                    handle = await environment.client.start_workflow(
                        "SignalDeckWorkflow",
                        spec.model_dump(mode="json", by_alias=True),
                        id=spec.run_id,
                        task_queue="cancel-test",
                    )
                    async with asyncio.timeout(15):
                        while True:
                            evidence = store.get_run(spec.run_id).evidence
                            if kind == "model" and len(calls) >= 2:
                                break
                            if kind == "deterministic" and any(
                                e.kind == "attempt" and e.status == "running" for e in evidence
                            ):
                                break
                            await asyncio.sleep(0.05)
                    await handle.cancel()
                    result = await asyncio.wait_for(handle.result(), timeout=8)
                    assert result["status"] == "cancelled", store.get_run(spec.run_id)
                    detail = store.get_run(spec.run_id)
                    assert all(e.status != "running" for e in detail.evidence), detail
                    assert {e.status for e in detail.evidence if e.kind in {"node", "agent"}} == {
                        "cancelled"
                    }
                    assert not any(tag == "B" for _, tag, _ in events)
                    if kind == "model":
                        assert (
                            len(
                                [
                                    e
                                    for e in detail.evidence
                                    if e.kind == "tool" and e.status == "succeeded"
                                ]
                            )
                            == 1
                        )
                        assert any(
                            e.kind == "model" and e.status == "cancelled" for e in detail.evidence
                        )
                    else:
                        assert any(
                            e.kind == "tool" and e.status == "unknown" for e in detail.evidence
                        )
                gate.set()
        engine.dispose()

    asyncio.run(scenario())


def test_total_deadline_stops_child_without_reset(database_url, tmp_path):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
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
                store, artifacts, lambda spec: transport, CORE, lambda: None
            )
            async with await create_worker(environment.client, services, "deadline-test"):
                spec = make_spec(
                    {
                        "a": {
                            "uses": "shared",
                            "inputMapping": mapping("A", {"value": 1}, 20),
                            "maxAttempts": 3,
                        },
                        "b": {
                            "uses": "shared",
                            "inputMapping": mapping("B", {"ref": "nodes.a.output.value"}),
                        },
                    },
                    deadline=3,
                )
                store.create_run(spec, spec.run_id)
                result = await asyncio.wait_for(
                    environment.client.execute_workflow(
                        "SignalDeckWorkflow",
                        spec.model_dump(mode="json", by_alias=True),
                        id=spec.run_id,
                        task_queue="deadline-test",
                    ),
                    timeout=9,
                )
                assert result["status"] == "failed"
                detail = store.get_run(spec.run_id)
                assert all(e.status != "running" for e in detail.evidence), detail
                assert not any(tag == "B" for _, tag, _ in events)
                assert any(e.kind == "node" and e.status == "timed_out" for e in detail.evidence)
        engine.dispose()

    asyncio.run(scenario())


def test_parent_cancellation_stops_parallel_model_tool_activities(database_url, tmp_path):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "parallel-tool-model-key"})
        events, calls = [], []
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
            async with await create_worker(environment.client, services, "parallel-tool-cancel"):
                spec = make_spec(
                    {
                        "a": {"uses": "shared", "inputMapping": mapping("A", {"value": 1}, 20)},
                        "b": {
                            "uses": "shared",
                            "inputMapping": mapping("B", {"ref": "nodes.a.output.value"}),
                        },
                    },
                    kind="model",
                    model_url=url,
                    model_store=store,
                )
                store.create_run(spec, spec.run_id)
                handle = await environment.client.start_workflow(
                    "SignalDeckWorkflow",
                    spec.model_dump(mode="json", by_alias=True),
                    id=spec.run_id,
                    task_queue="parallel-tool-cancel",
                )
                async with asyncio.timeout(15):
                    while len([event for event in events if event[0] == "start"]) < 2:
                        await asyncio.sleep(0.05)
                await handle.cancel()
                assert (await asyncio.wait_for(handle.result(), 8))["status"] == "cancelled"
                detail = store.get_run(spec.run_id)
                assert all(e.status != "running" for e in detail.evidence)
                assert {e.status for e in detail.evidence if e.kind in {"node", "agent"}} == {
                    "cancelled"
                }
                tools = [e for e in detail.evidence if e.kind == "tool"]
                assert len(tools) == 2 and all(e.status == "unknown" for e in tools)
                assert len(calls) == 1
                assert not any(tag == "B" for _, tag, _ in events)
        engine.dispose()

    asyncio.run(scenario())

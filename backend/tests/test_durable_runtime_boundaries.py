"""DAG failure semantics, bounded model loops and CAS execution histories."""

import asyncio
import os

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter, unpack_value
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


def test_missing_join_failure_and_large_model_tool_outputs(database_url, tmp_path):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts", inline_threshold=1024)
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
            model_server(calls) as url,
        ):
            services = TemporalServices(
                store, artifacts, lambda spec: transport, CORE, lambda: None
            )
            async with await create_worker(environment.client, services, "boundaries-test"):

                async def execute(spec):
                    store.create_run(spec, spec.run_id)
                    handle = await environment.client.start_workflow(
                        "SignalDeckWorkflow",
                        spec.model_dump(mode="json", by_alias=True),
                        id=spec.run_id,
                        task_queue="boundaries-test",
                    )
                    result = await asyncio.wait_for(handle.result(), 30)
                    return result, store.get_run(spec.run_id), handle

                spec = make_spec(
                    {
                        "a": {
                            "uses": "shared",
                            "inputMapping": mapping("skipped", {"value": 1}),
                            "condition": {"op": "eq", "args": [{"value": 1}, {"value": 2}]},
                        },
                        "b": {
                            "uses": "shared",
                            "acceptUpstreamStates": ["succeeded", "skipped"],
                            "inputMapping": mapping(
                                "joined", {"ref": "nodes.a.output.value", "onMissing": {"value": 5}}
                            ),
                        },
                    }
                )
                result, detail, _ = await execute(spec)
                assert result["status"] == "succeeded"
                skipped = next(e for e in detail.evidence if e.kind == "node" and e.node_id == "a")
                assert skipped.status == "skipped" and skipped.output is None
                assert result["output"]["value"] == 6

                spec = make_spec(
                    {
                        "a": {"uses": "shared", "inputMapping": mapping("FAIL", {"value": 1})},
                        "b": {
                            "uses": "shared",
                            "inputMapping": mapping("blocked", {"ref": "nodes.a.output.value"}),
                        },
                        "c": {
                            "uses": "shared",
                            "inputMapping": mapping("independent", {"value": 8}),
                        },
                    }
                )
                result, detail, _ = await execute(spec)
                assert result["status"] == "failed"
                states = {e.node_id: e.status for e in detail.evidence if e.kind == "node"}
                assert states == {"a": "failed", "b": "blocked", "c": "succeeded"}
                assert not any(tag == "blocked" for _, tag, _ in events)

                spec = make_spec(kind="model", model_url=url, model_store=store)
                spec.definition["agents"]["shared"]["budget"]["maxModelRequests"] = 1
                spec = recompile_spec(spec)
                before = len(calls)
                result, detail, _ = await execute(spec)
                assert result["status"] == "failed"
                assert len(calls) == before + 1
                assert len([e for e in detail.evidence if e.kind == "model"]) == 1

                wrong_core = make_spec().model_copy(update={"core_artifact": "sha256:" + "f" * 64})
                result, detail, _ = await execute(wrong_core)
                assert result["status"] == "failed"
                assert detail.error_code == "core_artifact_mismatch"
                assert detail.evidence
                assert all(
                    item.kind == "node" and item.status == "blocked" for item in detail.evidence
                )

                marker = "LARGE-CONTENT-" + "x" * 20000
                spec = make_spec(
                    {"a": {"uses": "shared", "inputMapping": mapping(marker, {"value": 4})}},
                    kind="model",
                    model_url=url,
                    model_store=store,
                )
                result, detail, _ = await execute(spec)
                assert result["status"] == "succeeded"
                assert set(result["output"]) == {"$artifact"}
                assert unpack_value(artifacts, result["output"])["tag"] == marker
                for item in detail.evidence:
                    if (
                        item.kind in {"node", "agent", "model", "tool"}
                        and item.status == "succeeded"
                    ):
                        assert isinstance(item.output, dict) and set(item.output) == {"$artifact"}
                child = environment.client.get_workflow_handle(f"{spec.run_id}:a:agent:1")
                history = await child.fetch_history()
                scheduled = {}
                offloaded = set()
                for event in history.events:
                    if event.HasField("activity_task_scheduled_event_attributes"):
                        attrs = event.activity_task_scheduled_event_attributes
                        scheduled[event.event_id] = attrs.activity_type.name
                        for value in attrs.input.payloads:
                            assert marker.encode() not in value.data
                    if event.HasField("activity_task_completed_event_attributes"):
                        attrs = event.activity_task_completed_event_attributes
                        name = scheduled[attrs.scheduled_event_id]
                        for value in attrs.result.payloads:
                            assert marker.encode() not in value.data
                            if value.metadata.get("encoding") == b"binary/signaldeck-artifact-v1":
                                offloaded.add(name)
                assert any(name.endswith("__model_request") for name in offloaded)
                assert any(name.endswith("__call_tool") for name in offloaded)
        engine.dispose()

    asyncio.run(scenario())

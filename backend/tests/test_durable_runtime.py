"""Real Temporal + PostgreSQL + MCP + OpenAI-compatible execution regressions."""

import asyncio
import os
from pathlib import Path

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment

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


def test_real_durable_dag_and_agent(database_url, tmp_path):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts", inline_threshold=1024)
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        events, calls = [], []
        cli = os.environ.get("TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal")
        assert Path(cli).is_file(), "TEMPORAL_CLI must point at pinned Temporal CLI 1.8.3"
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=cli,
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            tool_server(events) as transport,
            model_server(calls) as url,
        ):
            services = TemporalServices(
                store, artifacts, lambda spec: transport, CORE, lambda: None
            )
            worker = await create_worker(environment.client, services, "runtime-test")
            async with worker:
                nodes = {
                    "a": {"uses": "shared", "inputMapping": mapping("A", {"value": 1})},
                    "b": {
                        "uses": "shared",
                        "inputMapping": mapping("B", {"ref": "nodes.a.output.value"}, 0.1),
                    },
                    "c": {
                        "uses": "shared",
                        "inputMapping": mapping("C", {"ref": "nodes.a.output.value"}, 0.6),
                    },
                    "e": {
                        "uses": "shared",
                        "inputMapping": mapping("E", {"ref": "nodes.b.output.value"}),
                    },
                    "d": {
                        "uses": "shared",
                        "inputMapping": mapping("D", {"ref": "nodes.c.output.value"}),
                        "dependsOn": ["b"],
                    },
                }
                spec = make_spec(nodes)
                store.create_run(spec, spec.run_id)
                result = await environment.client.execute_workflow(
                    "SignalDeckWorkflow",
                    spec.model_dump(mode="json", by_alias=True),
                    id=spec.run_id,
                    task_queue="runtime-test",
                )
                assert result["status"] == "succeeded", store.get_run(spec.run_id)
                times = {(event, tag): at for event, tag, at in events}
                assert times["start", "C"] < times["end", "B"]
                assert times["start", "E"] < times["end", "C"]
                assert times["start", "D"] > times["end", "C"]
                detail = store.get_run(spec.run_id)
                assert all(e.status == "succeeded" for e in detail.evidence)
                assert {e.kind for e in detail.evidence} == {"node", "agent", "tool", "attempt"}
                store.save_resource("model", "model", {}, {"apiKey": "sentinel-model-credential"})
                spec = make_spec(kind="model", model_url=url, model_store=store)
                store.create_run(spec, spec.run_id)
                result = await environment.client.execute_workflow(
                    "SignalDeckWorkflow",
                    spec.model_dump(mode="json", by_alias=True),
                    id=spec.run_id,
                    task_queue="runtime-test",
                )
                assert result["status"] == "succeeded", store.get_run(spec.run_id)
                assert len(calls) == 2
                detail = store.get_run(spec.run_id)
                assert {e.kind for e in detail.evidence} == {
                    "node",
                    "agent",
                    "model",
                    "tool",
                    "attempt",
                }
                assert "sentinel-model-credential" not in detail.model_dump_json()
        engine.dispose()

    asyncio.run(scenario())


def test_worker_sigkill_reuses_confirmed_model_tool_and_sibling(database_url, tmp_path):
    import subprocess
    import sys

    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts", inline_threshold=1024)
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "sentinel-model-credential"})
        calls, events, gate = [], [], asyncio.Event()
        cli = os.environ.get("TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal")
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=cli,
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            tool_server(events, network=True) as endpoint,
            model_server(calls, gate=gate) as url,
        ):
            spec = make_spec(kind="model", model_url=url, model_store=store, deadline=90)
            payload = spec.model_dump(mode="json", by_alias=True)
            payload["pluginReleases"][0]["endpoint"] = endpoint
            # Add an independent deterministic sibling to the model Agent's parent Run.
            payload["definition"]["agents"]["plain"] = {
                **payload["definition"]["agents"]["shared"],
                "strategy": {
                    "kind": "deterministic",
                    "toolId": "example/probe/search",
                    "inputMapping": {"ref": "agent.input"},
                    "outputMapping": {"ref": "tool.output"},
                },
            }
            payload["definition"]["workflows"]["main"]["nodes"]["sibling"] = {
                "uses": "plain",
                "dependsOn": [],
                "inputMapping": mapping("sibling", {"value": 8}),
                "condition": None,
                "acceptUpstreamStates": ["succeeded"],
                "maxAttempts": 1,
            }
            payload["plan"]["nodeOrder"].append("sibling")
            payload["plan"]["dependencies"]["sibling"] = []
            spec = recompile_spec(type(spec).model_validate(payload))
            payload = spec.model_dump(mode="json", by_alias=True)
            store.create_run(spec, spec.run_id)
            env = dict(
                os.environ,
                PROBE_DATABASE=database_url,
                PROBE_ARTIFACTS=str(artifacts.root),
                PROBE_CORE=CORE,
                PROBE_ADDRESS=environment.client.service_client.config.target_host,
            )
            log = (tmp_path / "worker.log").open("w")

            def start():
                return subprocess.Popen(
                    [sys.executable, "-m", "tests.test_durable_runtime_worker"],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )

            process = start()
            try:
                handle = await environment.client.start_workflow(
                    "SignalDeckWorkflow",
                    payload,
                    id=spec.run_id,
                    task_queue="recovery-test",
                )
                async with asyncio.timeout(35):
                    while len(calls) < 2 or not any(
                        e.kind == "node" and e.node_id == "sibling" and e.status == "succeeded"
                        for e in store.get_run(spec.run_id).evidence
                    ):
                        assert process.poll() is None, (tmp_path / "worker.log").read_text()
                        await asyncio.sleep(0.05)
                before = store.get_run(spec.run_id)
                assert (
                    len(
                        [
                            e
                            for e in before.evidence
                            if e.kind == "model" and e.status == "succeeded"
                        ]
                    )
                    == 1
                )
                process.kill()
                process.wait()
                gate.set()
                process = start()
                result = await asyncio.wait_for(handle.result(), 40)
                assert result["status"] == "succeeded", store.get_run(spec.run_id)
                assert len(calls) == 3  # Only the unconfirmed second model network request repeats.
                assert [tag for kind, tag, _ in events if kind == "start"].count("A") == 1
                assert [tag for kind, tag, _ in events if kind == "start"].count("sibling") == 1
                detail = store.get_run(spec.run_id)
                assert all(e.status != "running" for e in detail.evidence)
                assert any(
                    e.kind == "attempt"
                    and e.status == "unknown"
                    and e.error_code == "worker_interrupted"
                    for e in detail.evidence
                )
                child = environment.client.get_workflow_handle(f"{spec.run_id}:a:agent:1")
                history = await child.fetch_history()
                (tmp_path / "recovery-history.json").write_text(history.to_json())
                assert "sentinel-model-credential" not in history.to_json()
                assert "binary/signaldeck-artifact-v1" in str(history.events)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                log.close()
        engine.dispose()

    asyncio.run(scenario())

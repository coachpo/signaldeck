"""Real Temporal + PostgreSQL + MCP + OpenAI-compatible execution regressions."""

import asyncio
import os
import shutil
from pathlib import Path

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.core_artifacts import CoreArtifactStore, task_queue
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import TemporalServices
from app.workers.durable_worker import create_worker
from tests.test_core_artifacts import publish_legacy_readme_bundle
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


def test_worker_sigkill_reuses_confirmed_model_tool_and_sibling_across_readme_publication(
    database_url, tmp_path
):
    import subprocess
    import sys

    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts", inline_threshold=1024)
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "sentinel-model-credential"})
        backend = Path(__file__).resolve().parents[1]
        source = tmp_path / "source"
        shutil.copytree(
            backend / "app", source / "app", ignore=shutil.ignore_patterns("__pycache__")
        )
        for name in ["pyproject.toml", "uv.lock", "README.md", "VERSION"]:
            shutil.copyfile(backend / name, source / name)
        core = CoreArtifactStore(tmp_path / "core", source)
        old = publish_legacy_readme_bundle(core)
        assert "README.md" in old.manifest["files"]
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
            spec = make_spec(kind="model", model_url=url, model_store=store, deadline=180)
            payload = spec.model_dump(mode="json", by_alias=True)
            payload["coreArtifact"] = old.digest
            payload["pluginReleases"][0]["endpoint"] = endpoint
            # Exercise artifact-backed child history with the production worker's
            # default payload threshold, rather than the test worker's smaller one.
            payload["definition"]["agents"]["shared"]["strategy"]["prompt"] += " context" * 9000
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
                DATABASE_URL=database_url,
                SIGNALDECK_ARTIFACT_DIR=str(artifacts.root),
                SIGNALDECK_CORE_ARTIFACT_DIR=str(core.root),
                SIGNALDECK_CORE_ENV_DIR=str(tmp_path / "environments"),
                TEMPORAL_ADDRESS=environment.client.service_client.config.target_host,
                SIGNALDECK_RUNTIME_MODE="test",
                LOGFIRE_SEND_TO_LOGFIRE="false",
            )
            log = (tmp_path / "worker.log").open("w")

            def start(digest):
                return subprocess.Popen(
                    [sys.executable, "-m", "app.workers.artifact_worker", "--digest", digest],
                    cwd=backend,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )

            process = start(old.digest)
            try:
                handle = await environment.client.start_workflow(
                    "SignalDeckWorkflow",
                    payload,
                    id=spec.run_id,
                    task_queue=task_queue(old.digest),
                )
                async with asyncio.timeout(65):
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
                (source / "README.md").write_text("# Updated documentation\n")
                new = core.publish()
                assert new.digest != old.digest
                assert "README.md" not in new.manifest["files"]
                assert core.verify(old.digest) == old
                (source / "README.md").write_text("# Further documentation update\n")
                assert core.current_digest() == new.digest
                gate.set()
                process = start(old.digest)
                result = await asyncio.wait_for(handle.result(), 65)
                assert result["status"] == "succeeded", store.get_run(spec.run_id)
                assert len(calls) == 3  # Only the unconfirmed second model network request repeats.
                assert [tag for kind, tag, _ in events if kind == "start"].count("A") == 1
                assert [tag for kind, tag, _ in events if kind == "start"].count("sibling") == 1
                detail = store.get_run(spec.run_id)
                assert detail.spec.core_artifact == old.digest
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
                newer = make_spec(deadline=90).model_copy(update={"core_artifact": new.digest})
                newer.plugin_releases[0]["endpoint"] = endpoint
                store.create_run(newer, newer.run_id)
                new_process = start(new.digest)
                try:
                    new_result = await asyncio.wait_for(
                        environment.client.execute_workflow(
                            "SignalDeckWorkflow",
                            newer.model_dump(mode="json", by_alias=True),
                            id=newer.run_id,
                            task_queue=task_queue(new.digest),
                        ),
                        65,
                    )
                    assert new_result["status"] == "succeeded", store.get_run(newer.run_id)
                    assert store.get_run(newer.run_id).spec.core_artifact == new.digest
                    assert core.verify(old.digest) == old
                finally:
                    new_process.terminate()
                    try:
                        new_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        new_process.kill()
                        new_process.wait()
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

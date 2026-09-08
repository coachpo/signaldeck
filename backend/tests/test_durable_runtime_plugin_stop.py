"""A stopped platform run must retain uncertainty about an independent write."""

import asyncio
import json
import os
import socket
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment

from app.domain.schema_contract import materialize_schema
from app.domain.tool_contracts import ToolCatalog, tool_contract_digest
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.mcp_transport import EmptySecretResolver, McpToolTransport
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import TemporalServices
from app.workers.durable_worker import create_worker
from tests.test_durable_runtime_support import CORE, make_release, make_spec, mapping


async def until_file(path, process):
    async with asyncio.timeout(20):
        while not path.exists():
            assert process.poll() is None, "Owned plugin exited unexpectedly"
            await asyncio.sleep(0.025)


@asynccontextmanager
async def held_plugin(directory, cooperative):
    root = Path(__file__).resolve().parents[2]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    release = make_release()
    tool = release.tools[0].model_copy(
        update={
            "input_schema": materialize_schema(release.tools[0].input_schema),
            "output_schema": materialize_schema(release.tools[0].output_schema),
            "effect": "write",
            "max_attempts": 2,
        }
    )
    release = release.model_copy(
        update={
            "endpoint": f"http://127.0.0.1:{port}/mcp/",
            "tools": (tool,),
            "contract_digest": tool_contract_digest((tool,)),
            "supports_operation_query": True,
            "supports_operation_deduplication": False,
        }
    )
    (directory / "release.json").write_text(release.model_dump_json(by_alias=True))
    with (directory / "plugin.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "held_plugin:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
                "--timeout-graceful-shutdown",
                "2",
            ],
            cwd=directory,
            env={
                **os.environ,
                "HELD_PLUGIN_STATE": str(directory),
                "HELD_PLUGIN_COOPERATIVE": "1" if cooperative else "0",
                "PYTHONPATH": os.pathsep.join(
                    [str(root / "plugins/runtime"), str(root / "backend/tests/fixtures")]
                ),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            async with httpx.AsyncClient() as client, asyncio.timeout(20):
                while True:
                    assert process.poll() is None, (directory / "plugin.log").read_text()
                    try:
                        response = await client.get(f"http://127.0.0.1:{port}/health", timeout=0.2)
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.025)
            yield release, process
        finally:
            (directory / "release").touch()
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, timeout=5)


@pytest.mark.parametrize("stop", ["cancel", "deadline"])
@pytest.mark.parametrize("cooperative", [True, False])
def test_independent_plugin_receives_cancellation_without_false_effect_confirmation(
    database_url, tmp_path, stop, cooperative
):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        try:
            async with (
                held_plugin(tmp_path, cooperative) as (release, process),
                await WorkflowEnvironment.start_local(
                    dev_server_existing_path=os.environ.get(
                        "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                    ),
                    data_converter=create_data_converter(artifacts),
                    plugins=[PydanticAIPlugin()],
                ) as environment,
            ):
                services = TemporalServices(
                    store,
                    artifacts,
                    lambda _: McpToolTransport(EmptySecretResolver()),
                    CORE,
                    lambda: None,
                )
                async with await create_worker(environment.client, services, "independent-stop"):
                    spec = make_spec(
                        {
                            "a": {"uses": "shared", "inputMapping": mapping("held", {"value": 1})},
                            "b": {
                                "uses": "shared",
                                "inputMapping": mapping(
                                    "forbidden", {"ref": "nodes.a.output.value"}
                                ),
                            },
                        },
                        deadline=5 if stop == "deadline" else 30,
                    )
                    catalog = ToolCatalog((release,))
                    spec = spec.model_copy(
                        update={
                            "plugin_releases": [release.model_dump(mode="json", by_alias=True)],
                            "tool_aliases": {
                                item["name"]: catalog.resolve_alias(item["name"])
                                for item in catalog.model_tools((release.tools[0].tool_id,))
                            },
                        }
                    )
                    store.create_run(spec, spec.run_id)
                    handle = await environment.client.start_workflow(
                        "SignalDeckWorkflow",
                        spec.model_dump(mode="json", by_alias=True),
                        id=spec.run_id,
                        task_queue="independent-stop",
                    )
                    await until_file(tmp_path / "started.json", process)
                    if stop == "cancel":
                        requested = store.request_cancel(spec.run_id)
                        assert requested.status == "running"
                        assert requested.cancel_requested_at is not None
                        await handle.cancel()
                    result = await asyncio.wait_for(handle.result(), timeout=12)
                    assert result["status"] == ("cancelled" if stop == "cancel" else "failed")
                    before_effect = store.get_run(spec.run_id)
                    tool = next(item for item in before_effect.evidence if item.kind == "tool")
                    assert tool.status == "unknown" and tool.output is None
                    assert all(item.status != "running" for item in before_effect.evidence)
                    downstream = next(
                        item
                        for item in before_effect.evidence
                        if item.kind == "node" and item.node_id == "b"
                    )
                    assert downstream.status in {"cancelled", "timed_out", "blocked"}
                    assert downstream.output is None
                    assert not (tmp_path / "effect.json").exists()
                    assert process.poll() is None
                    if cooperative:
                        await until_file(tmp_path / "cancelled.json", process)
                    (tmp_path / "release").touch()
                    if cooperative:
                        effect = None
                        assert not (tmp_path / "effect.json").exists()
                    else:
                        await until_file(tmp_path / "effect.json", process)
                        effect = json.loads((tmp_path / "effect.json").read_text())
                        assert effect["operationId"] == tool.operation_id
                        assert effect["output"]["value"] == 2
                    assert store.get_run(spec.run_id) == before_effect
                    requests = [
                        json.loads(line)
                        for line in (tmp_path / "requests.jsonl").read_text().splitlines()
                    ]
                    effects = [
                        item
                        for item in requests
                        if item.get("method") == "tools/call"
                        and item["params"]["name"] == release.tools[0].tool_id
                    ]
                    assert len(effects) == 1
                    assert (
                        len([item for item in requests if item.get("method") == "tools/call"]) == 1
                    )
                    cancellations = [
                        item for item in requests if item.get("method") == "notifications/cancelled"
                    ]
                    assert len(cancellations) == 1
                    assert cancellations[0]["params"]["requestId"] == effects[0]["id"]
                    assert set(cancellations[0]["params"]) == {"requestId", "reason"}
                    (tmp_path / "observation.json").write_text(
                        json.dumps(
                            {
                                "stop": stop,
                                "cooperative": cooperative,
                                "platformStatus": before_effect.status,
                                "toolStatus": tool.status,
                                "toolErrorCode": tool.error_code,
                                "effectAfterPlatformStop": effect,
                                "receivedMethods": [item.get("method") for item in requests],
                            },
                            indent=2,
                        )
                    )
        finally:
            engine.dispose()

    asyncio.run(scenario())

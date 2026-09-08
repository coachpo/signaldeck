"""Actual Worker isolation across dynamic contracts and unusable unrelated plugins."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import ValidationError
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.testing import WorkflowEnvironment

from app.api.platform_dependencies import get_launch_service, get_platform_store
from app.application.definitions import save_definition
from app.application.launch import LaunchService
from app.domain.schema_contract import materialize_schema, validate_value
from app.domain.tool_contracts import PluginRelease, ToolDefinition, tool_contract_digest
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.mcp_transport import CONTEXT_META, RELEASE_META, McpToolTransport
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import FrozenSecretResolver, TemporalServices
from app.main import create_app
from app.workers.durable_worker import create_worker
from tests.test_durable_runtime_support import CORE, model_server, serve_app
from tests.test_platform_api import FixedCore


def schema(lane: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {lane: {"type": "integer" if lane == "number" else "string"}},
        "required": [lane],
    }


def definition(lane: str, tool_id: str) -> str:
    return json.dumps(
        {
            "apiVersion": "signaldeck.workflowPackage/v2",
            "metadata": {"key": "dynamic", "name": "Dynamic contracts"},
            "agents": {
                "shared": {
                    "inputSchema": schema(lane),
                    "outputSchema": schema(lane),
                    "strategy": {
                        "kind": "model",
                        "modelRef": "model",
                        "prompt": "Call the supplied tool once and return its JSON result.",
                    },
                    "tools": [tool_id],
                    "resources": ["workspace"],
                    "budget": {"deadlineSeconds": 40},
                }
            },
            "workflows": {
                "main": {
                    "inputSchema": schema(lane),
                    "outputSchema": schema(lane),
                    "nodes": {
                        "work": {"uses": "shared", "inputMapping": {"ref": "workflow.input"}}
                    },
                    "outputMapping": {"ref": "nodes.work.output"},
                    "deadlineSeconds": 40,
                }
            },
        }
    )


@asynccontextmanager
async def contract_server(lane: str, arrivals: dict[str, asyncio.Event], dispatches: list):
    tool = ToolDefinition(
        tool_id=f"example/dynamic/{lane}_lookup",
        owner_plugin_id="example/dynamic",
        input_schema=schema(lane),
        output_schema=schema(lane),
        resource_requirements=("workspace",),
    )
    release = PluginRelease(
        plugin_id="example/dynamic",
        release_id=lane,
        artifact_digest="sha256:" + ("b" if lane == "number" else "c") * 64,
        endpoint="http://127.0.0.1/mcp",
        config_schema={
            "type": "object",
            "properties": {"lane": {"type": "string", "enum": [lane]}},
            "required": ["lane"],
        },
        tools=(tool,),
        contract_digest=tool_contract_digest((tool,)),
    )
    server = Server("dynamic-contract", version=lane)
    identity = {
        "pluginId": release.plugin_id,
        "releaseId": release.release_id,
        "artifactDigest": release.artifact_digest,
        "contractDigest": release.contract_digest,
    }

    @server.list_tools()
    async def list_tools(request: types.ListToolsRequest) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=tool.tool_id,
                    inputSchema=materialize_schema(tool.input_schema),
                    outputSchema=materialize_schema(tool.output_schema),
                )
            ],
            _meta={RELEASE_META: identity},
        )

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]):
        meta = server.request_context.meta.model_dump(by_alias=True)
        context = meta[CONTEXT_META]
        assert name == tool.tool_id
        assert meta[RELEASE_META] == identity
        assert context["toolGrants"] == [tool.tool_id]
        assert context["resourceBindings"] == {"workspace": {"lane": lane}}
        validate_value(tool.input_schema, arguments)
        dispatches.append({"toolId": name, "arguments": arguments, "context": context})
        arrivals[lane].set()
        # Both independent calls must reach their real endpoints before either finishes.
        await asyncio.wait_for(
            asyncio.gather(*(event.wait() for event in arrivals.values())), timeout=15
        )
        return (
            {"number": arguments["number"] + 100}
            if lane == "number"
            else {"text": arguments["text"].upper()}
        )

    manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)
    async with manager.run(), serve_app(manager.handle_request) as endpoint:
        yield release.model_copy(update={"endpoint": endpoint})


def prepare_run(store: PlatformStore, release: PluginRelease, model_url: str):
    lane = release.release_id
    store.install_plugin(release.plugin_id, release.model_dump(mode="json", by_alias=True))
    store.save_resource(
        "workspace", "tool", {"pluginId": release.plugin_id, "scope": {"lane": lane}}
    )
    store.save_resource("model", "model", {"baseUrl": model_url, "modelId": lane})
    save_definition(store, definition(lane, release.tools[0].tool_id))
    parameters = {"number": 7} if lane == "number" else {"text": "separate"}
    launched = LaunchService(store, FixedCore()).launch("dynamic", "main", parameters)
    return store.get_run(launched.id).spec


def runtime(store: PlatformStore, artifacts: ArtifactStore) -> TemporalServices:
    return TemporalServices(
        store,
        artifacts,
        lambda bindings: McpToolTransport(
            FrozenSecretResolver(store.resolve_bound_credentials, bindings)
        ),
        CORE,
        lambda: None,
    )


def test_one_worker_isolates_concurrent_frozen_dynamic_schemas_and_bindings(
    session_factory, tmp_path
):
    async def scenario():
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(session_factory, artifacts=artifacts)
        store.initialize()
        calls, dispatches = [], []
        arrivals = {lane: asyncio.Event() for lane in ("number", "text")}
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=os.environ.get(
                    "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                ),
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            model_server(calls) as url,
            contract_server("number", arrivals, dispatches) as number_release,
            contract_server("text", arrivals, dispatches) as text_release,
        ):
            specs = [prepare_run(store, release, url) for release in (number_release, text_release)]
            assert specs[0].package_hash != specs[1].package_hash
            assert store.get_package("dynamic")["packageHash"] == specs[1].package_hash
            assert store.list_plugins()[0]["release"]["releaseId"] == "text"
            worker = await create_worker(environment.client, runtime(store, artifacts), "dynamic")
            async with worker:
                results = await asyncio.wait_for(
                    asyncio.gather(
                        *(
                            environment.client.execute_workflow(
                                "SignalDeckWorkflow",
                                spec.model_dump(mode="json", by_alias=True),
                                id=spec.run_id,
                                task_queue="dynamic",
                            )
                            for spec in specs
                        )
                    ),
                    timeout=35,
                )
            assert [result["status"] for result in results] == ["succeeded", "succeeded"]
            assert [result["output"] for result in results] == [
                {"number": 107},
                {"text": "SEPARATE"},
            ]
            assert all(event.is_set() for event in arrivals.values())
            assert len(dispatches) == 2
            assert len(calls) == 4
            for lane, spec, expected in zip(
                ("number", "text"), specs, ({"number": 107}, {"text": "SEPARATE"}), strict=True
            ):
                alias, tool_id = next(iter(spec.tool_aliases.items()))
                own_calls = [call for call in calls if call["model"] == lane]
                assert len(own_calls) == 2
                for call in own_calls:
                    assert [tool["function"]["name"] for tool in call["tools"]] == [alias]
                    assert call["tools"][0]["function"]["parameters"] == materialize_schema(
                        schema(lane)
                    )
                actual = next(
                    item for item in dispatches if item["context"]["runId"] == spec.run_id
                )
                assert actual["toolId"] == tool_id
                assert actual["arguments"] == spec.parameters
                detail = store.get_run(spec.run_id)
                assert detail.output == expected
                assert detail.spec.resource_bindings["workspace"]["scope"] == {"lane": lane}
                assert detail.spec.model_bindings["model"]["modelId"] == lane
                tools = [item for item in detail.evidence if item.kind == "tool"]
                assert len(tools) == 1
                assert tools[0].tool_id == tool_id
                assert tools[0].output == expected
                assert all(item.run_id == spec.run_id for item in detail.evidence)

    asyncio.run(scenario())


@pytest.mark.parametrize("enabled", [False, True], ids=["disabled", "enabled-but-unused"])
def test_malformed_unrelated_plugin_does_not_initialize_on_reads_or_block_agent(
    session_factory, tmp_path, enabled
):
    async def scenario():
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(session_factory, artifacts=artifacts)
        store.initialize()
        calls, dispatches, unwanted_requests = [], [], []
        failed_plugin = FastAPI()

        @failed_plugin.api_route("/{path:path}", methods=["GET", "POST", "DELETE"])
        async def fail(path: str):
            unwanted_requests.append(path)
            return JSONResponse(status_code=503, content={"error": "unavailable"})

        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=os.environ.get(
                    "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                ),
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            model_server(calls) as url,
            serve_app(failed_plugin) as broken_endpoint,
            contract_server("number", {"number": asyncio.Event()}, dispatches) as release,
        ):
            malformed = {"artifactDigest": "sha256:" + "d" * 64, "endpoint": broken_endpoint}
            with pytest.raises(ValidationError):
                PluginRelease.model_validate(malformed)
            # Persisted corruption bypasses install validation to exercise read/launch isolation.
            store.install_plugin("unused/broken", malformed, enabled=enabled)
            spec = prepare_run(store, release, url)
            app = create_app(init_database=False)
            app.dependency_overrides[get_platform_store] = lambda: store
            app.dependency_overrides[get_launch_service] = lambda: LaunchService(store, FixedCore())
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://core.test"
            ) as client:
                for path in (
                    "/health",
                    "/ready",
                    "/api/plugins",
                    "/api/resources",
                    "/api/workflow-packages",
                    "/api/runs",
                    f"/api/runs/{spec.run_id}",
                ):
                    response = await client.get(path)
                    assert response.status_code == 200, response.text
                worker = await create_worker(
                    environment.client, runtime(store, artifacts), "offline"
                )
                async with worker:
                    result = await asyncio.wait_for(
                        environment.client.execute_workflow(
                            "SignalDeckWorkflow",
                            spec.model_dump(mode="json", by_alias=True),
                            id=spec.run_id,
                            task_queue="offline",
                        ),
                        timeout=30,
                    )
                assert result["status"] == "succeeded"
                assert result["output"] == {"number": 107}
                history = await client.get(f"/api/runs/{spec.run_id}")
                assert history.status_code == 200
                assert history.json()["status"] == "succeeded"
                assert {item["pluginId"] for item in history.json()["spec"]["pluginReleases"]} == {
                    "example/dynamic"
                }
                assert len(dispatches) == 1 and len(calls) == 2
                assert unwanted_requests == []

    asyncio.run(scenario())

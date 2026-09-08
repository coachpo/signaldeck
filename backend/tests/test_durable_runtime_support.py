"""Isolated protocol fixtures for the real Temporal execution integration tests."""

from __future__ import annotations

import asyncio
import json
import socket
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from app.domain.compiler import compile_package
from app.domain.execution import ResolvedRunSpec
from app.domain.schema_contract import materialize_schema
from app.domain.tool_contracts import (
    PluginRelease,
    ToolCatalog,
    ToolDefinition,
    tool_contract_digest,
)
from app.infrastructure.mcp_transport import RELEASE_META, EmptySecretResolver, McpToolTransport

SCHEMA = {
    "type": "object",
    "properties": {
        "value": {"type": "integer"},
        "delay": {"type": "number"},
        "tag": {"type": "string"},
    },
    "required": ["value", "delay", "tag"],
}
CORE = "sha256:" + "a" * 64


def make_release() -> PluginRelease:
    tool = ToolDefinition(
        tool_id="example/probe/search",
        owner_plugin_id="example/probe",
        input_schema=SCHEMA,
        output_schema=SCHEMA,
    )
    return PluginRelease(
        plugin_id="example/probe",
        release_id="v1",
        artifact_digest="sha256:" + "b" * 64,
        endpoint="http://local.test/mcp",
        tools=(tool,),
        contract_digest=tool_contract_digest((tool,)),
    )


def mapping(tag: str, value: dict[str, Any], delay: float = 0) -> dict[str, Any]:
    return {"object": {"value": value, "delay": {"value": delay}, "tag": {"value": tag}}}


def make_spec(nodes=None, *, kind="deterministic", model_url=None, model_store=None, deadline=30):
    strategy = {"kind": "deterministic", "toolId": "example/probe/search"}
    if kind == "model":
        strategy = {"kind": "model", "modelRef": "model", "prompt": "Call the supplied tool once."}
    definition = {
        "apiVersion": "signaldeck.workflowPackage/v2",
        "metadata": {"key": "probe", "name": "Probe"},
        "agents": {
            "shared": {
                "inputSchema": SCHEMA,
                "outputSchema": SCHEMA,
                "strategy": strategy,
                "tools": ["example/probe/search"],
                "budget": {"deadlineSeconds": deadline},
            }
        },
        "workflows": {
            "main": {
                "inputSchema": {"type": "object"},
                "outputSchema": SCHEMA,
                "nodes": nodes
                or {"a": {"uses": "shared", "inputMapping": mapping("A", {"value": 1})}},
                "outputMapping": {
                    "ref": "nodes." + (list(nodes)[-1] if nodes else "a") + ".output"
                },
                "deadlineSeconds": deadline,
            }
        },
    }
    compiled = compile_package(definition)
    release = make_release()
    catalog = ToolCatalog((release,))
    return ResolvedRunSpec(
        run_id=str(uuid4()),
        package_key="probe",
        workflow_key="main",
        package_hash=compiled.content_hash,
        definition=compiled.package.model_dump(mode="json", by_alias=True),
        plan=compiled.plans["main"].model_dump(mode="json", by_alias=True),
        parameters={},
        core_artifact=CORE,
        deadline=datetime.now(UTC) + timedelta(seconds=deadline),
        plugin_releases=[release.model_dump(mode="json", by_alias=True)],
        model_bindings=(
            {
                "model": {
                    "baseUrl": model_url,
                    "modelId": "probe",
                    "apiStyle": "chat_completions",
                    "timeoutSeconds": 10,
                    "credentialRevision": model_store.get_resource("model")["credentialRevision"],
                }
            }
            if model_url
            else {}
        ),
        tool_aliases={
            item["name"]: catalog.resolve_alias(item["name"])
            for item in catalog.model_tools(("example/probe/search",))
        },
    )


@asynccontextmanager
async def tool_server(events, *, network=False, offset=1):
    release = make_release()
    definition = release.tools[0]
    server = Server("probe", version="v1")
    ready_e = asyncio.Event()
    ready_c = asyncio.Event()

    @server.list_tools()
    async def list_tools(request: types.ListToolsRequest) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=definition.tool_id,
                    inputSchema=materialize_schema(SCHEMA),
                    outputSchema=materialize_schema(SCHEMA),
                )
            ],
            _meta={
                RELEASE_META: {
                    "pluginId": release.plugin_id,
                    "releaseId": release.release_id,
                    "artifactDigest": release.artifact_digest,
                    "contractDigest": release.contract_digest,
                }
            },
        )

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]):
        events.append(("start", arguments["tag"], asyncio.get_running_loop().time()))
        try:
            if arguments["tag"] == "FAIL":
                raise ValueError("controlled plugin failure")
            if arguments["tag"] == "E":
                ready_e.set()
            if arguments["tag"] == "B":
                await asyncio.wait_for(ready_c.wait(), timeout=10)
            if arguments["tag"] == "C":
                ready_c.set()
                await asyncio.wait_for(ready_e.wait(), timeout=10)
            await asyncio.sleep(arguments["delay"])
            events.append(("end", arguments["tag"], asyncio.get_running_loop().time()))
            return {**arguments, "value": arguments["value"] + offset}
        except asyncio.CancelledError:
            events.append(("cancel", arguments["tag"], asyncio.get_running_loop().time()))
            raise

    manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)
    async with manager.run():
        if network:
            async with serve_app(manager.handle_request) as url:
                yield url
        else:
            yield McpToolTransport(
                EmptySecretResolver(), httpx.ASGITransport(app=manager.handle_request)
            )


@asynccontextmanager
async def model_server(calls, *, gate=None, tool_calls=1, fail_count=0, credential_log=None):
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def completion(request: Request):
        body = await request.json()
        if credential_log is not None:
            credential_log.append(request.headers.get("authorization"))
        calls.append(body)
        if len(calls) <= fail_count:
            return JSONResponse(
                status_code=503, content={"error": {"message": "controlled failure"}}
            )
        tool_returns = [m for m in body["messages"] if m["role"] == "tool"]
        if tool_returns:
            if gate is not None:
                await gate.wait()
            message = {"role": "assistant", "content": tool_returns[-1]["content"]}
            reason = "stop"
        else:
            prompt = json.loads(next(m["content"] for m in body["messages"] if m["role"] == "user"))
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call-{index}",
                        "type": "function",
                        "function": {
                            "name": body["tools"][0]["function"]["name"],
                            "arguments": json.dumps(prompt["input"]),
                        },
                    }
                    for index in range(tool_calls)
                ],
            }
            reason = "tool_calls"
        return {
            "id": "chatcmpl-probe",
            "object": "chat.completion",
            "created": 0,
            "model": "probe",
            "choices": [{"index": 0, "message": message, "finish_reason": reason}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 8, "total_tokens": 16},
        }

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app, log_level="error", interface="asgi3", lifespan="off", timeout_graceful_shutdown=2
        )
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        await asyncio.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}/v1"
    finally:
        if gate is not None:
            gate.set()
        server.should_exit = True
        await task


@asynccontextmanager
async def serve_app(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app, log_level="error", interface="asgi3", lifespan="off", timeout_graceful_shutdown=2
        )
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        await asyncio.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


def recompile_spec(spec):
    compiled = compile_package(spec.definition)
    return spec.model_copy(
        update={
            "definition": compiled.package.model_dump(mode="json", by_alias=True),
            "package_hash": compiled.content_hash,
            "plan": compiled.plans[spec.workflow_key].model_dump(mode="json", by_alias=True),
        }
    )

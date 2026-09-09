"""MCP transport and immutable release identity; contains no business dispatch registry."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import anyio
from fastapi import FastAPI
from jsonschema import Draft202012Validator
from mcp import types
from mcp.server.lowlevel import Server
from plugin_runtime.sessions import PluginSessions
from starlette.routing import Mount

PROTOCOL = "2025-11-25"
CONTEXT_FIELDS = {
    "runId",
    "nodeId",
    "invocationId",
    "operationId",
    "deadline",
    "toolGrants",
    "resourceGrants",
    "resourceBindings",
}


def digest(value):
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
    )


def artifact_digest(roots: list[Path]) -> str:
    """Identity includes every distributed source, web asset and dependency lock."""
    files = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_file() and not any(
                p in {"__pycache__", ".venv", ".git"} for p in path.parts
            ):
                files[root.name + "/" + str(path.relative_to(root))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    return digest(files)


def obj(properties=None, required=()):
    return {
        "type": "object",
        "properties": properties or {},
        "required": list(required),
        "unevaluatedProperties": False,
    }


def tool(
    plugin_id,
    name,
    input_schema,
    output_schema,
    description,
    *,
    write=False,
    resources=(),
    result_links=None,
):
    return {
        "toolId": f"{plugin_id}/{name}",
        "ownerPluginId": plugin_id,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": output_schema,
        "effect": "write" if write else "read",
        "resourceRequirements": list(resources),
        "timeoutSeconds": 30.0,
        "maxAttempts": 2 if write else 1,
        **({"resultLinks": result_links} if result_links is not None else {}),
    }


def release(
    plugin_id,
    version,
    endpoint,
    tools,
    roots,
    page_url=None,
    configuration=None,
    config_schema=None,
):
    for url in (endpoint, page_url):
        if url is None:
            continue
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Plugin URLs must not contain credentials, queries or fragments"
            )
    result = {
        "pluginId": plugin_id,
        "releaseId": version,
        "artifactDigest": (
            digest({"artifact": artifact_digest(roots), "configuration": configuration})
            if configuration is not None
            else artifact_digest(roots)
        ),
        "endpoint": endpoint,
        "protocolVersion": PROTOCOL,
        "configSchema": config_schema or obj(),
        "tools": tools,
        "contractDigest": digest(sorted(tools, key=lambda item: item["toolId"])),
        "supportsOperationQuery": True,
        "supportsOperationDeduplication": True,
    }
    if page_url:
        result["pageUrl"] = page_url
    return result


def application(
    binding: dict,
    execute: Callable,
    query: Callable,
    *,
    startup: Callable | None = None,
) -> FastAPI:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    identity = {
        key: binding[key]
        for key in ("pluginId", "releaseId", "artifactDigest", "contractDigest")
    }
    server = Server(binding["pluginId"], version=binding["releaseId"])
    definitions = {item["toolId"]: item for item in binding["tools"]}

    @server.list_tools()
    async def list_tools(request: types.ListToolsRequest) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=t["toolId"],
                    description=t["description"],
                    inputSchema=t["inputSchema"],
                    outputSchema=t["outputSchema"],
                )
                for t in definitions.values()
            ]
            + [
                types.Tool(
                    name="signaldeck/operations/query",
                    description="Resolve an issued operation without repeating its effect.",
                    inputSchema=obj(
                        {
                            "operationId": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                            }
                        },
                        ("operationId",),
                    ),
                )
            ],
            _meta={"signaldeck/release": identity},
        )

    # Validate explicitly to keep raw arguments out of protocol error messages.
    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict):
        try:
            metadata = server.request_context.meta
            metadata = metadata.model_dump(by_alias=True) if metadata else {}
            if metadata.get("signaldeck/release") != identity:
                raise ValueError("release_binding_mismatch")
            context = metadata.get("signaldeck/context")
            if not isinstance(context, dict) or set(context) != CONTEXT_FIELDS:
                raise ValueError("invalid_invocation_context")
            if datetime.fromisoformat(
                context["deadline"].replace("Z", "+00:00")
            ) <= datetime.now(UTC):
                raise ValueError("deadline_exceeded")
            if name == "signaldeck/operations/query":
                if (
                    set(arguments) != {"operationId"}
                    or arguments["operationId"] != context["operationId"]
                ):
                    raise ValueError("invalid_operation_query")
                result = await anyio.to_thread.run_sync(
                    query,
                    arguments["operationId"],
                    context["resourceBindings"],
                    context["toolGrants"],
                )
            else:
                definition = definitions.get(name)
                if definition is None or name not in context["toolGrants"]:
                    raise ValueError("tool_not_granted")
                for resource_id in definition["resourceRequirements"]:
                    resource = context["resourceBindings"].get(resource_id)
                    if resource_id not in context["resourceGrants"] or not isinstance(
                        resource, dict
                    ):
                        raise ValueError("resource_not_granted")
                if list(
                    Draft202012Validator(definition["inputSchema"]).iter_errors(
                        arguments
                    )
                ):
                    raise ValueError("invalid_tool_input")
                result = await anyio.to_thread.run_sync(
                    execute, name, arguments, context
                )
                if list(
                    Draft202012Validator(definition["outputSchema"]).iter_errors(result)
                ):
                    raise ValueError("invalid_tool_output")
            return types.CallToolResult(content=[], structuredContent=result)
        except Exception:
            # Exception messages may contain upstream headers, credentials, or supplied arguments.
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text", text="Plugin call rejected or failed"
                    )
                ],
                isError=True,
            )

    # Keep request association across POSTs so MCP cancellation reaches the in-flight call.
    manager = PluginSessions(server)

    @asynccontextmanager
    async def lifespan(app):
        if startup:
            await anyio.to_thread.run_sync(startup)
        async with manager.run():
            yield

    app = FastAPI(title=binding["pluginId"], lifespan=lifespan)
    app.state.execute = execute

    from starlette.exceptions import HTTPException
    from starlette.responses import JSONResponse

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(
            {
                "code": "plugin_request_error",
                "message": "Plugin request rejected",
                "details": [],
            },
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.get("/health")
    def health():
        return {"status": "ok", "releaseId": binding["releaseId"]}

    @app.get("/release")
    def descriptor():
        return binding

    async def mcp(scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            protocol = headers.get(b"mcp-protocol-version")
            if protocol and protocol.decode() != PROTOCOL:
                await JSONResponse(
                    {
                        "code": "unsupported_protocol",
                        "message": "MCP protocol version mismatch",
                        "details": [],
                    },
                    status_code=400,
                )(scope, receive, send)
                return
        await manager.handle_request(scope, receive, send)

    app.router.routes.append(Mount("/mcp", app=mcp))
    return app

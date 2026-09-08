"""MCP Streamable HTTP I/O against the exact frozen plugin release."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from opentelemetry.trace import SpanKind, StatusCode

from app.domain.execution import ApplicationError
from app.domain.schema_contract import materialize_schema
from app.domain.tool_contracts import (
    PluginRelease,
    ToolDefinition,
    ToolInvocationContext,
    ToolResult,
)
from app.infrastructure.execution_tracing import TraceParentPropagator, execution_tracer
from app.infrastructure.mcp_cancellation import ToolRequestCancellation

RELEASE_META = "signaldeck/release"
CONTEXT_META = "signaldeck/context"
OPERATION_QUERY_TOOL = "signaldeck/operations/query"


class SecretResolver(Protocol):
    async def resolve(self, plugin_id: str, resource_refs: tuple[str, ...]) -> dict[str, str]:
        """Resolve only authorized references into request headers at the I/O boundary."""
        ...


class EmptySecretResolver:
    async def resolve(self, plugin_id: str, resource_refs: tuple[str, ...]) -> dict[str, str]:
        if resource_refs:
            raise ValueError("Resource binding unavailable")
        return {}


class McpToolTransport:
    def __init__(
        self, secrets: SecretResolver, http_transport: httpx.AsyncBaseTransport | None = None
    ):
        self.secrets = secrets
        self.http_transport = http_transport

    async def execute(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        arguments: dict[str, Any],
        context: ToolInvocationContext,
    ) -> ToolResult:
        return await self._call(release, tool, arguments, context, query=False)

    async def query(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        context: ToolInvocationContext,
    ) -> ToolResult:
        return await self._call(
            release, tool, {"operationId": context.operation_id}, context, query=True
        )

    async def verify_release(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        context: ToolInvocationContext,
    ) -> ToolResult:
        return await self._call(release, tool, {}, context, query=False, verify_only=True)

    async def _call(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        arguments: dict[str, Any],
        context: ToolInvocationContext,
        *,
        query: bool,
        verify_only: bool = False,
    ) -> ToolResult:
        name = (
            "mcp.verify_release"
            if verify_only
            else "mcp.query_operation" if query else "mcp.call_tool"
        )
        with execution_tracer().start_as_current_span(
            name,
            kind=SpanKind.CLIENT,
            attributes={
                "signaldeck.run_id": context.run_id,
                "signaldeck.node_id": context.node_id,
                "signaldeck.invocation_id": context.invocation_id,
                "signaldeck.operation_id": context.operation_id,
                "signaldeck.tool_id": tool.tool_id,
                "signaldeck.plugin_id": release.plugin_id,
            },
        ) as span:
            result = await self._request(
                release, tool, arguments, context, query=query, verify_only=verify_only
            )
            if result.status in {"failed", "unknown"}:
                span.set_status(StatusCode.ERROR)
            return result

    async def _request(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        arguments: dict[str, Any],
        context: ToolInvocationContext,
        *,
        query: bool,
        verify_only: bool = False,
    ) -> ToolResult:
        try:
            headers = await self.secrets.resolve(release.plugin_id, tool.resource_requirements)
        except ApplicationError as exc:
            code = (
                "resource_binding_changed"
                if exc.code == "resource_binding_changed"
                else "credential_unavailable"
            )
            return ToolResult(status="failed", code=code)
        except Exception:
            return ToolResult(status="failed", code="credential_unavailable")
        cancellation = ToolRequestCancellation()
        try:
            if any(
                name.lower().startswith("mcp-")
                or name.lower() in {"traceparent", "tracestate", "baggage"}
                for name in headers
            ):
                return ToolResult(status="failed", code="invalid_resource_headers")
            trace_headers: dict[str, str] = {}
            TraceParentPropagator().inject(trace_headers)
            async with httpx.AsyncClient(
                headers={**headers, **trace_headers},
                transport=self.http_transport,
                follow_redirects=False,
                timeout=httpx.Timeout(tool.timeout_seconds),
                event_hooks={"request": [cancellation.observe_request]},
            ) as client:
                async with streamable_http_client(release.endpoint, http_client=client) as streams:
                    async with ClientSession(streams[0], streams[1]) as session:
                        initialized = await session.initialize()
                        if initialized.protocolVersion != release.protocol_version:
                            return ToolResult(status="failed", code="plugin_protocol_mismatch")
                        catalog = await session.list_tools()
                        if not self._matches(
                            release, catalog.model_dump(mode="json", by_alias=True)
                        ):
                            return ToolResult(status="failed", code="plugin_release_unavailable")
                        if verify_only:
                            return ToolResult(
                                status="succeeded",
                                output={
                                    "pluginId": release.plugin_id,
                                    "releaseId": release.release_id,
                                    "artifactDigest": release.artifact_digest,
                                    "contractDigest": release.contract_digest,
                                },
                            )
                        scoped = context.model_copy(
                            update={
                                "tool_grants": (tool.tool_id,),
                                "resource_grants": tool.resource_requirements,
                            }
                        )
                        wire_context = scoped.model_dump(mode="json", by_alias=True)
                        wire_context.pop("cachePolicy", None)
                        wire_context["resourceBindings"] = {
                            resource_id: context.resource_bindings[resource_id]["scope"]
                            for resource_id in tool.resource_requirements
                        }
                        response = await cancellation.call_tool(
                            session,
                            client,
                            release.endpoint,
                            release.protocol_version,
                            streams[2],
                            OPERATION_QUERY_TOOL if query else tool.tool_id,
                            arguments,
                            metadata={
                                CONTEXT_META: wire_context,
                                RELEASE_META: {
                                    "pluginId": release.plugin_id,
                                    "releaseId": release.release_id,
                                    "artifactDigest": release.artifact_digest,
                                    "contractDigest": release.contract_digest,
                                },
                            },
                        )
                        raw = response.model_dump(mode="json", by_alias=True)
                        if _contains_credential(raw, tuple(headers.values())):
                            return ToolResult(
                                status="unknown", code="plugin_response_contains_credential"
                            )
                        if response.isError:
                            # MCP errors do not establish whether a business write was applied.
                            return ToolResult(status="unknown", code="plugin_operation_error")
                        if response.structuredContent is None:
                            return ToolResult(
                                status="unknown", code="plugin_structured_output_missing"
                            )
                        if query:
                            outcome = ToolResult.model_validate(response.structuredContent)
                            return outcome.model_copy(
                                update={
                                    "code": "operation_query_result" if outcome.code else None,
                                    "cache_provenance": None,
                                }
                            )
                        return ToolResult(status="succeeded", output=response.structuredContent)
        except Exception:
            if cancellation.cancelled:
                # A racing cancellation response can make SDK teardown raise a stream
                # error. Preserve cancellation instead of scheduling reconciliation.
                raise asyncio.CancelledError from None
            if verify_only:
                return ToolResult(status="failed", code="plugin_release_unavailable")
            return ToolResult(status="unknown", code="plugin_transport_interrupted", retryable=True)

    @staticmethod
    def _matches(release: PluginRelease, catalog: dict[str, Any]) -> bool:
        metadata = (catalog.get("_meta") or {}).get(RELEASE_META)
        expected = {
            "pluginId": release.plugin_id,
            "releaseId": release.release_id,
            "artifactDigest": release.artifact_digest,
            "contractDigest": release.contract_digest,
        }
        if metadata != expected or catalog.get("nextCursor"):
            return False
        advertised = {tool["name"]: tool for tool in catalog["tools"]}
        expected_names = {tool.tool_id for tool in release.tools}
        if release.supports_operation_query:
            expected_names.add(OPERATION_QUERY_TOOL)
        if set(advertised) != expected_names or len(advertised) != len(catalog["tools"]):
            return False
        return all(
            advertised[tool.tool_id]["inputSchema"] == materialize_schema(tool.input_schema)
            and advertised[tool.tool_id].get("outputSchema")
            == materialize_schema(tool.output_schema)
            for tool in release.tools
        )


def _contains_credential(value: Any, header_values: tuple[str, ...]) -> bool:
    fragments = set(header_values)
    for header in header_values:
        parts = header.split(None, 1)
        if len(parts) == 2 and parts[0].lower() in {"bearer", "basic"}:
            fragments.add(parts[1])
    fragments.discard("")

    def contains(item: Any) -> bool:
        if isinstance(item, str):
            return any(fragment in item for fragment in fragments)
        if isinstance(item, dict):
            return any(contains(key) or contains(child) for key, child in item.items())
        if isinstance(item, (list, tuple)):
            return any(contains(child) for child in item)
        return False

    return contains(value)

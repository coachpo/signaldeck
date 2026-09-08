from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from app.application.tool_gateway import ToolGateway
from app.domain.schema_contract import materialize_schema
from app.domain.tool_contracts import (
    PluginRelease,
    ToolCatalog,
    ToolDefinition,
    ToolInvocationContext,
    ToolResult,
    tool_contract_digest,
)
from app.infrastructure.mcp_transport import RELEASE_META, EmptySecretResolver, McpToolTransport

SCHEMA = {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}


def tool(effect="read", owner="example/probe", **kwargs):
    return ToolDefinition(
        tool_id=owner + "/search",
        owner_plugin_id=owner,
        input_schema=SCHEMA,
        output_schema=SCHEMA,
        effect=effect,
        **kwargs,
    )


def release(definition, **kwargs):
    return PluginRelease(
        plugin_id=definition.owner_plugin_id,
        release_id="v1",
        artifact_digest="sha256:" + "a" * 64,
        endpoint="http://localhost/mcp",
        tools=(definition,),
        contract_digest=tool_contract_digest((definition,)),
        **kwargs,
    )


def context(definition, operation="operation-1", **kwargs):
    return ToolInvocationContext(
        run_id="run-1",
        node_id="node-1",
        invocation_id="invocation-1",
        operation_id=operation,
        deadline=datetime.now(UTC) + timedelta(minutes=1),
        tool_grants=(definition.tool_id,),
        **kwargs,
    )


class Evidence:
    def __init__(self):
        self.operations = {}
        self.attempts = []
        self.owned_operations = set()

    @asynccontextmanager
    async def operation_guard(self, operation_id, deadline):
        if operation_id in self.owned_operations:
            yield False
            return
        self.owned_operations.add(operation_id)
        try:
            yield True
        finally:
            self.owned_operations.remove(operation_id)

    async def get_operation(self, operation_id):
        return self.operations.get(operation_id)

    async def count_execute_attempts(self, operation_id):
        return sum(item[0] == operation_id and item[2] == "execute" for item in self.attempts)

    async def reserve_operation(self, operation):
        if operation.context.operation_id in self.operations:
            return False
        self.operations[operation.context.operation_id] = operation
        return True

    async def begin_attempt(self, operation_id, kind):
        previous = self.operations[operation_id]
        number = previous.attempts + 1
        self.operations[operation_id] = previous.model_copy(update={"attempts": number})
        self.attempts.append((operation_id, number, kind))
        return number

    async def finish_attempt(self, operation_id, attempt, result):
        self.attempts.append((operation_id, attempt, result))

    async def finish_operation(self, operation_id, result):
        previous = self.operations[operation_id]
        assert previous.status != "succeeded" or previous.result == result
        self.operations[operation_id] = previous.model_copy(
            update={"status": result.status, "result": result}
        )


class Transport:
    def __init__(self, outcomes, query=None):
        self.outcomes = list(outcomes)
        self.queries = 0
        self.calls = 0
        self.query_result = query or ToolResult(status="unknown")

    async def execute(self, release, tool, arguments, context):
        self.calls += 1
        result = self.outcomes.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    async def query(self, release, tool, context):
        self.queries += 1
        return self.query_result


def test_catalog_qualified_aliases_and_defensive_snapshot():
    first, second = tool(), tool(owner="other/probe")
    catalog = ToolCatalog((release(first), release(second)))
    names = catalog.model_tools((first.tool_id, second.tool_id))
    assert len({item["name"] for item in names}) == 2
    assert {catalog.resolve_alias(item["name"]) for item in names} == {
        first.tool_id,
        second.tool_id,
    }
    first.input_schema["properties"]["value"]["type"] = "string"
    names[0]["parameters"]["properties"].clear()
    assert catalog.binding(second.tool_id)[1].input_schema == SCHEMA
    with pytest.raises(ValueError):
        catalog.resolve_alias("search")


def test_unauthorized_and_schema_invalid_requests_never_dispatch():
    async def scenario():
        definition = tool(resource_requirements=("resource-1",))
        transport, evidence = Transport([]), Evidence()
        gateway = ToolGateway(ToolCatalog((release(definition),)), transport, evidence)
        invocation = context(definition)
        assert (
            await gateway.call(definition.tool_id, {"value": 1}, invocation)
        ).code == "resource_not_granted"
        assert (
            await gateway.call(definition.tool_id, {"value": "bad"}, invocation)
        ).code == "invalid_tool_input"
        assert (
            await gateway.call("other/probe/search", {"value": 1}, invocation)
        ).code == "tool_not_granted"
        assert transport.calls == 0 and not evidence.operations

    asyncio.run(scenario())


def test_confirmed_results_reused_only_for_same_operation_identity():
    async def scenario():
        definition = tool()
        transport, evidence = (
            Transport([ToolResult(status="succeeded", output={"value": 2})]),
            Evidence(),
        )
        gateway = ToolGateway(ToolCatalog((release(definition),)), transport, evidence)
        invocation = context(definition)
        assert (await gateway.call(definition.tool_id, {"value": 1}, invocation)).output == {
            "value": 2
        }
        assert (await gateway.call(definition.tool_id, {"value": 1}, invocation)).output == {
            "value": 2
        }
        assert (
            await gateway.call(definition.tool_id, {"value": 2}, invocation)
        ).code == "operation_identity_conflict"
        assert transport.calls == 1

    asyncio.run(scenario())


def test_write_response_lost_queries_before_any_retry_and_preserves_unknown():
    async def scenario():
        definition = tool("write", max_attempts=3)
        transport, evidence = Transport([TimeoutError("sensitive-response")]), Evidence()
        gateway = ToolGateway(ToolCatalog((release(definition),)), transport, evidence)
        invocation = context(definition)
        result = await gateway.call(definition.tool_id, {"value": 1}, invocation)
        assert result.status == "unknown"
        assert (
            await gateway.call(definition.tool_id, {"value": 1}, invocation)
        ).status == "unknown"
        assert transport.calls == 1 and "sensitive" not in result.model_dump_json()
        transport.query_result = ToolResult(status="succeeded", output={"value": 3})
        recovered = ToolGateway(
            ToolCatalog((release(definition, supports_operation_query=True),)), transport, evidence
        )
        assert (await recovered.call(definition.tool_id, {"value": 1}, invocation)).output == {
            "value": 3
        }
        assert transport.calls == 1 and transport.queries == 1

    asyncio.run(scenario())


def test_output_validation_and_deadline_are_enforced():
    async def scenario():
        definition = tool()
        transport, evidence = (
            Transport([ToolResult(status="succeeded", output={"value": "bad"})]),
            Evidence(),
        )
        gateway = ToolGateway(ToolCatalog((release(definition),)), transport, evidence)
        assert (
            await gateway.call(definition.tool_id, {"value": 1}, context(definition))
        ).code == "invalid_tool_output"
        expired = context(definition, "expired").model_copy(
            update={"deadline": datetime.now(UTC) - timedelta(seconds=1)}
        )
        assert (
            await gateway.call(definition.tool_id, {"value": 1}, expired)
        ).code == "deadline_exceeded"
        assert transport.calls == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("changed_release", [False, True])
def test_real_mcp_streamable_http_release_and_schema_verification(changed_release):
    async def scenario():
        definition = tool()
        frozen = release(definition)
        server = Server("probe", version="v1")
        seen = []

        @server.list_tools()
        async def list_tools(request: types.ListToolsRequest) -> types.ListToolsResult:
            return types.ListToolsResult(
                tools=[
                    types.Tool(
                        name=definition.tool_id,
                        inputSchema=materialize_schema(definition.input_schema),
                        outputSchema=materialize_schema(definition.output_schema),
                    )
                ],
                _meta={
                    RELEASE_META: {
                        "pluginId": frozen.plugin_id,
                        "releaseId": "v2" if changed_release else frozen.release_id,
                        "artifactDigest": frozen.artifact_digest,
                        "contractDigest": frozen.contract_digest,
                    }
                },
            )

        @server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]):
            seen.append(server.request_context.meta.model_dump(by_alias=True))
            return {"value": arguments["value"] + 1}

        manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)
        async with manager.run():
            transport = McpToolTransport(
                EmptySecretResolver(), httpx.ASGITransport(app=manager.handle_request)
            )
            outcome = await transport.execute(frozen, definition, {"value": 2}, context(definition))
        if changed_release:
            assert outcome.code == "plugin_release_unavailable"
            assert not seen
        else:
            assert outcome.status == "succeeded", outcome
            assert outcome.output == {"value": 3}
            assert seen[0]["signaldeck/context"]["operationId"] == "operation-1"

    asyncio.run(scenario())


def test_cancelled_write_records_unknown_before_propagating_cancellation():
    async def scenario():
        definition = tool("write")
        evidence = Evidence()
        entered = asyncio.Event()

        class BlockingTransport(Transport):
            async def execute(self, release, tool, arguments, context):
                entered.set()
                await asyncio.Event().wait()

        gateway = ToolGateway(ToolCatalog((release(definition),)), BlockingTransport([]), evidence)
        invocation = context(definition)
        pending = asyncio.create_task(gateway.call(definition.tool_id, {"value": 1}, invocation))
        await entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        persisted = evidence.operations[invocation.operation_id]
        assert persisted.status == "unknown"
        assert persisted.result.code == "cancelled_effect_unconfirmed"
        assert evidence.attempts[-1][2].status == "unknown"

    asyncio.run(scenario())


def test_recovery_after_deadline_preserves_unconfirmed_write_effect():
    async def scenario():
        definition = tool("write")
        evidence = Evidence()
        invocation = context(definition).model_copy(
            update={"deadline": datetime.now(UTC) - timedelta(seconds=1)}
        )
        from app.domain.tool_contracts import ToolOperationRecord, canonical_digest

        await evidence.reserve_operation(
            ToolOperationRecord(
                context=invocation,
                tool_id=definition.tool_id,
                input_digest=canonical_digest({"value": 1}),
            )
        )
        gateway = ToolGateway(ToolCatalog((release(definition),)), Transport([]), evidence)
        result = await gateway.call(definition.tool_id, {"value": 1}, invocation)
        assert result.status == "unknown" and result.code == "deadline_effect_unconfirmed"
        assert not evidence.attempts

    asyncio.run(scenario())


def test_plugin_endpoint_rejects_embedded_credentials():
    definition = tool()
    for endpoint in [
        "http://user:password@localhost/mcp",
        "http://localhost/mcp?token=secret",
        "file:///tmp/mcp",
    ]:
        with pytest.raises(ValueError):
            PluginRelease.model_validate({**release(definition).model_dump(), "endpoint": endpoint})


def test_mcp_negotiated_protocol_must_match_frozen_protocol(monkeypatch):
    async def scenario():
        definition = tool()
        server = Server("old-protocol")
        manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)
        monkeypatch.setattr(types, "LATEST_PROTOCOL_VERSION", "2025-06-18")
        async with manager.run():
            transport = McpToolTransport(
                EmptySecretResolver(), httpx.ASGITransport(app=manager.handle_request)
            )
            result = await transport.execute(
                release(definition), definition, {"value": 1}, context(definition)
            )
        assert result.code == "plugin_protocol_mismatch"

    asyncio.run(scenario())


def test_dynamic_catalogs_do_not_share_mutable_schemas_or_alias_dispatch():
    a = tool()
    b = a.model_copy(deep=True)
    b.input_schema["properties"]["value"] = {"type": "string"}
    first, second = ToolCatalog((release(a),)), ToolCatalog((release(b),))
    assert (
        first.model_tools((a.tool_id,))[0]["parameters"]["properties"]["value"]["type"] == "integer"
    )
    assert (
        second.model_tools((a.tool_id,))[0]["parameters"]["properties"]["value"]["type"] == "string"
    )


@pytest.mark.parametrize("leaks_secret", [False, "value", "metadata_key"])
@pytest.mark.parametrize(
    "credential", ["Bearer test-only-private-credential", 'Bearer escaped"credential\\line']
)
def test_mcp_credentials_resolve_only_at_io_and_never_enter_results_or_context(
    leaks_secret, credential, caplog
):
    async def scenario():
        schema = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }
        definition = ToolDefinition(
            tool_id="example/private/search",
            owner_plugin_id="example/private",
            input_schema=schema,
            output_schema=schema,
            resource_requirements=("credential-ref",),
        )
        frozen = release(definition)
        server = Server("private-probe", version="v1")
        resolved = []
        contexts = []

        class Resolver:
            async def resolve(self, plugin_id, resource_refs):
                resolved.append((plugin_id, resource_refs))
                return {"Authorization": credential}

        @server.list_tools()
        async def list_tools(request: types.ListToolsRequest) -> types.ListToolsResult:
            return types.ListToolsResult(
                tools=[
                    types.Tool(
                        name=definition.tool_id,
                        inputSchema=materialize_schema(schema),
                        outputSchema=materialize_schema(schema),
                    )
                ],
                _meta={
                    RELEASE_META: {
                        "pluginId": frozen.plugin_id,
                        "releaseId": frozen.release_id,
                        "artifactDigest": frozen.artifact_digest,
                        "contractDigest": frozen.contract_digest,
                    }
                },
            )

        @server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]):
            contexts.append(server.request_context.meta.model_dump(by_alias=True))
            if leaks_secret == "metadata_key":
                return types.CallToolResult(
                    content=[],
                    structuredContent={"value": "safe"},
                    _meta={credential.removeprefix("Bearer "): "value"},
                )
            return {"value": credential.removeprefix("Bearer ") if leaks_secret else "safe"}

        manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)
        async with manager.run():
            transport = McpToolTransport(
                Resolver(), httpx.ASGITransport(app=manager.handle_request)
            )
            invocation = context(
                definition,
                resource_grants=("credential-ref", "unrelated-ref"),
                resource_bindings={
                    "credential-ref": {
                        "pluginId": definition.owner_plugin_id,
                        "scope": {"collection": "research"},
                    }
                },
            )
            outcome = await transport.execute(frozen, definition, {"value": "safe"}, invocation)
        assert resolved == [(definition.owner_plugin_id, ("credential-ref",))]
        assert contexts[0]["signaldeck/context"]["resourceGrants"] == ["credential-ref"]
        assert contexts[0]["signaldeck/release"]["artifactDigest"] == frozen.artifact_digest
        assert (
            credential.removeprefix("Bearer ")
            not in str(contexts) + outcome.model_dump_json() + caplog.text
        )
        if leaks_secret:
            assert outcome.status == "unknown" and outcome.output is None
        else:
            assert outcome.output == {"value": "safe"}

    asyncio.run(scenario())


def test_tool_scalar_output_requires_explicit_plugin_object_contract():
    with pytest.raises(ValueError, match="MCP structuredContent"):
        ToolDefinition(
            tool_id="example/probe/scalar",
            owner_plugin_id="example/probe",
            input_schema=SCHEMA,
            output_schema={"type": "string"},
        )


def test_gateway_requires_frozen_owner_binding_and_records_safe_arguments():
    async def scenario():
        definition = tool(resource_requirements=("workspace",))
        transport, evidence = (
            Transport([ToolResult(status="succeeded", output={"value": 2})]),
            Evidence(),
        )
        gateway = ToolGateway(ToolCatalog((release(definition),)), transport, evidence)
        missing = context(definition, resource_grants=("workspace",))
        assert (
            await gateway.call(definition.tool_id, {"value": 1}, missing)
        ).code == "resource_binding_unavailable"
        wrong = context(
            definition,
            resource_grants=("workspace",),
            resource_bindings={
                "workspace": {"pluginId": "other/plugin", "scope": {"collection": "research"}}
            },
        )
        assert (
            await gateway.call(definition.tool_id, {"value": 1}, wrong)
        ).code == "resource_binding_unavailable"
        correct = context(
            definition,
            resource_grants=("workspace",),
            resource_bindings={
                "workspace": {
                    "pluginId": definition.owner_plugin_id,
                    "scope": {"collection": "research"},
                }
            },
        )
        arguments = {"value": 1}
        assert (await gateway.call(definition.tool_id, arguments, correct)).status == "succeeded"
        arguments["value"] = 100
        assert evidence.operations[correct.operation_id].arguments == {"value": 1}
        assert evidence.operations[correct.operation_id].context.resource_bindings["workspace"][
            "scope"
        ] == {"collection": "research"}

    asyncio.run(scenario())


def test_sensitive_scope_fields_are_rejected_before_snapshot_or_io():
    definition = tool()
    with pytest.raises(ValueError, match="credential fields"):
        context(
            definition,
            resource_grants=("workspace",),
            resource_bindings={
                "workspace": {
                    "pluginId": definition.owner_plugin_id,
                    "scope": {"apiKey": "private"},
                }
            },
        )


def test_default_tool_contract_digest_is_stable_through_frozen_json_roundtrip():
    definition = tool()
    frozen = release(definition)
    restored = PluginRelease.model_validate_json(frozen.model_dump_json(by_alias=True))
    assert restored.contract_digest == tool_contract_digest(restored.tools)
    assert restored.model_dump(mode="json", by_alias=True) == frozen.model_dump(
        mode="json", by_alias=True
    )
    assert (
        ToolCatalog((restored,)).binding(definition.tool_id)[0].contract_digest
        == frozen.contract_digest
    )


@pytest.mark.parametrize("binding_changed", [False, True])
def test_credential_resolution_failures_are_known_before_network_and_never_reconcile_write(
    binding_changed,
):
    from app.domain.execution import ApplicationError

    async def scenario():
        class Resolver:
            async def resolve(self, plugin_id, resource_refs):
                if binding_changed:
                    raise ApplicationError("resource_binding_changed", "private diagnostic")
                raise RuntimeError("private diagnostic")

        async def unexpected_http(request):
            pytest.fail("Credential rejection must precede every HTTP request")

        definition = tool("write", max_attempts=3)
        transport = McpToolTransport(Resolver(), httpx.MockTransport(unexpected_http))
        evidence = Evidence()
        gateway = ToolGateway(
            ToolCatalog((release(definition, supports_operation_query=True),)), transport, evidence
        )
        invocation = context(definition)
        result = await gateway.call(definition.tool_id, {"value": 1}, invocation)
        assert result.status == "failed"
        assert result.code == (
            "resource_binding_changed" if binding_changed else "credential_unavailable"
        )
        assert "private diagnostic" not in result.model_dump_json()
        assert [item[2] for item in evidence.attempts if isinstance(item[2], str)] == ["execute"]
        verified = await transport.verify_release(release(definition), definition, invocation)
        assert verified == result

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "query_support,dedupe_support,expected_status",
    [
        (True, False, "failed"),
        (False, True, "unknown"),
        (False, False, "unknown"),
    ],
)
def test_exhausted_write_budget_distinguishes_confirmed_absence_from_dedupe_permission(
    query_support, dedupe_support, expected_status
):
    async def scenario():
        definition = tool("write", max_attempts=1)
        transport = Transport([TimeoutError()], query=ToolResult(status="not_found"))
        evidence = Evidence()
        frozen = release(
            definition,
            supports_operation_query=query_support,
            supports_operation_deduplication=dedupe_support,
        )
        gateway = ToolGateway(ToolCatalog((frozen,)), transport, evidence)
        invocation = context(definition)
        result = await gateway.call(definition.tool_id, {"value": 1}, invocation)
        assert result.status == expected_status and not result.retryable
        assert result.output is None
        assert transport.calls == 1 and transport.queries == int(query_support)
        assert await evidence.count_execute_attempts(invocation.operation_id) == 1
        recovered = await gateway.call(definition.tool_id, {"value": 1}, invocation)
        assert recovered.status == expected_status and transport.calls == 1
        assert {item[0] for item in evidence.attempts} == {invocation.operation_id}

    asyncio.run(scenario())


def test_query_network_attempts_do_not_consume_business_write_retry_budget():
    async def scenario():
        definition = tool("write", max_attempts=2)
        transport = Transport([TimeoutError(), ToolResult(status="succeeded", output={"value": 2})])
        evidence = Evidence()
        gateway = ToolGateway(
            ToolCatalog((release(definition, supports_operation_query=True),)), transport, evidence
        )
        invocation = context(definition)
        assert (
            await gateway.call(definition.tool_id, {"value": 1}, invocation)
        ).status == "unknown"
        assert transport.calls == 1 and transport.queries == 1
        transport.query_result = ToolResult(status="not_found")
        result = await gateway.call(definition.tool_id, {"value": 1}, invocation)
        assert result.status == "succeeded" and result.output == {"value": 2}
        assert transport.calls == 2 and transport.queries == 2
        assert (await evidence.get_operation(invocation.operation_id)).attempts == 4
        assert await evidence.count_execute_attempts(invocation.operation_id) == 2
        assert await gateway.call(definition.tool_id, {"value": 1}, invocation) == result
        assert transport.calls == 2 and transport.queries == 2

    asyncio.run(scenario())


def test_write_effect_before_deadline_response_loss_stays_unknown_without_replay():
    async def scenario():
        effects = []

        class AppliedWrite(Transport):
            async def execute(self, release, tool, arguments, context):
                self.calls += 1
                effects.append(context.operation_id)
                await asyncio.Event().wait()

        definition = tool("write", max_attempts=3)
        transport, evidence = AppliedWrite([]), Evidence()
        gateway = ToolGateway(
            ToolCatalog((release(definition, supports_operation_query=True),)), transport, evidence
        )
        invocation = context(definition).model_copy(
            update={"deadline": datetime.now(UTC) + timedelta(milliseconds=80)}
        )
        result = await gateway.call(definition.tool_id, {"value": 1}, invocation)
        assert effects == [invocation.operation_id]
        assert result.status == "unknown" and result.code == "deadline_effect_unconfirmed"
        assert transport.calls == 1 and transport.queries == 0
        assert evidence.attempts[-1][2].status == "unknown"
        assert (await evidence.get_operation(invocation.operation_id)).status == "unknown"
        assert (
            await gateway.call(definition.tool_id, {"value": 1}, invocation)
        ).status == "unknown"
        assert transport.calls == 1 and transport.queries == 0

    asyncio.run(scenario())

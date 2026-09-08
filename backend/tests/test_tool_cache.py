"""Explicit cross-run read caching through the real PostgreSQL evidence boundary."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.responses import Response

from app.application.tool_gateway import ToolGateway
from app.domain.execution import ExecutionEvidence, ResolvedRunSpec
from app.domain.tool_contracts import (
    PluginRelease,
    ToolCatalog,
    ToolDefinition,
    ToolInvocationContext,
    ToolReadCachePolicy,
    ToolResult,
    tool_contract_digest,
)
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.evidence_store import PostgresToolEvidenceStore
from app.infrastructure.platform_models import OperationRow
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.resource_limiter import PostgresResourceLimiter
from app.infrastructure.tool_cache_store import PostgresToolCacheStore, ToolCacheRow

SCHEMA = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}


def definition(effect="read", resources=()):
    return ToolDefinition(
        tool_id="example/cache/fetch",
        owner_plugin_id="example/cache",
        input_schema=SCHEMA,
        output_schema=SCHEMA,
        effect=effect,
        resource_requirements=resources,
    )


def release(tool, digest="a"):
    return PluginRelease(
        plugin_id=tool.owner_plugin_id,
        release_id="v1",
        endpoint="http://localhost/mcp",
        artifact_digest="sha256:" + digest * 64,
        tools=(tool,),
        contract_digest=tool_contract_digest((tool,)),
    )


class Transport:
    def __init__(self):
        self.calls = 0

    async def execute(self, release, tool, arguments, context):
        self.calls += 1
        return ToolResult(status="succeeded", output={"value": f"fresh-{self.calls}:" + "x" * 150})

    async def verify_release(self, release, tool, context):
        return ToolResult(status="succeeded", output={"artifactDigest": release.artifact_digest})

    async def query(self, release, tool, context):
        raise AssertionError("Read tools do not reconcile write effects")


@pytest.fixture
def storage(database_url, tmp_path):
    engine = create_engine(database_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    artifacts = ArtifactStore(tmp_path, inline_threshold=40)
    platform = PlatformStore(factory, artifacts)
    platform.initialize()
    cache = PostgresToolCacheStore(factory, artifacts)
    cache.initialize()
    yield platform, PostgresToolEvidenceStore(factory, artifacts), cache
    engine.dispose()


def prepare(platform, run_id, tool, policy=None, bindings=None):
    due = datetime.now(UTC) + timedelta(minutes=1)
    platform.create_run(
        ResolvedRunSpec(
            run_id=run_id,
            package_key="cache",
            workflow_key="main",
            package_hash="sha256:test",
            definition={},
            plan={},
            parameters={},
            core_artifact="sha256:core",
            deadline=due,
        ),
        "launch:" + run_id,
    )
    platform.record_evidence(
        ExecutionEvidence(
            id="node:" + run_id, run_id=run_id, node_id="node", kind="node", status="running"
        )
    )
    platform.record_evidence(
        ExecutionEvidence(
            id="agent:" + run_id,
            run_id=run_id,
            node_id="node",
            parent_id="node:" + run_id,
            kind="agent",
            status="running",
        )
    )
    return ToolInvocationContext(
        run_id=run_id,
        node_id="node",
        invocation_id="agent:" + run_id,
        operation_id="op:" + run_id,
        deadline=due,
        tool_grants=(tool.tool_id,),
        cache_policy=policy,
        resource_grants=tool.resource_requirements,
        resource_bindings=bindings or {},
    )


def test_explicit_cache_preserves_source_cas_and_default_new_run_freshness(storage):
    async def scenario():
        platform, evidence, cache = storage
        tool = definition()
        transport = Transport()
        gateway = ToolGateway(ToolCatalog((release(tool),)), transport, evidence, cache=cache)
        policy = ToolReadCachePolicy(ttl_seconds=60)
        first = prepare(platform, "first", tool, policy)
        original = await gateway.call(tool.tool_id, {"value": "input"}, first)
        assert original.cache_provenance.hit is False
        assert original.cache_provenance.source_run_id == "first"
        assert (
            original.cache_provenance.expires_at - original.cache_provenance.fetched_at
        ).total_seconds() == 60
        default = prepare(platform, "default", tool)
        uncached = await gateway.call(tool.tool_id, {"value": "input"}, default)
        assert uncached.output != original.output and uncached.cache_provenance is None
        selected = prepare(platform, "selected", tool, policy)
        cached = await gateway.call(tool.tool_id, {"value": "input"}, selected)
        assert cached.output == original.output and cached.cache_provenance.hit
        assert cached.cache_provenance.source_operation_id == first.operation_id
        assert cached.cache_provenance.fetched_at == original.cache_provenance.fetched_at
        assert transport.calls == 2
        projected = platform.get_run("selected")
        projected_tool = next(
            item for item in projected.evidence if item.id == selected.operation_id
        )
        assert projected_tool.metadata["cacheProvenance"]["hit"] is True
        assert projected_tool.metadata["cacheProvenance"]["sourceRunId"] == "first"
        assert await gateway.call(tool.tool_id, {"value": "input"}, first) == original
        assert transport.calls == 2
        with platform.session_factory() as session:
            first_payload = session.get(OperationRow, first.operation_id).payload
            hit_payload = session.get(OperationRow, selected.operation_id).payload
            assert first_payload["result"]["output"] == hit_payload["result"]["output"]
            assert set(first_payload["result"]["output"]) == {"$artifact"}
            assert hit_payload["result"]["cacheProvenance"]["hit"] is True
            assert len(list(session.scalars(select(ToolCacheRow)))) == 1

    asyncio.run(scenario())


def test_input_release_and_ttl_bound_cache_reuse(storage):
    async def scenario():
        platform, evidence, cache = storage
        tool, transport = definition(), Transport()
        gateway = ToolGateway(ToolCatalog((release(tool),)), transport, evidence, cache=cache)
        policy = ToolReadCachePolicy(ttl_seconds=1)
        first = prepare(platform, "first", tool, policy)
        result = await gateway.call(tool.tool_id, {"value": "one"}, first)
        await gateway.call(tool.tool_id, {"value": "two"}, prepare(platform, "input", tool, policy))
        changed = ToolGateway(ToolCatalog((release(tool, "b"),)), transport, evidence, cache=cache)
        await changed.call(
            tool.tool_id, {"value": "one"}, prepare(platform, "release", tool, policy)
        )
        assert transport.calls == 3
        # Await the source's declared wall-clock expiration rather than assuming a polling count.
        await asyncio.sleep(
            max(0, (result.cache_provenance.expires_at - datetime.now(UTC)).total_seconds()) + 0.01
        )
        expired = await gateway.call(
            tool.tool_id, {"value": "one"}, prepare(platform, "expired", tool, policy)
        )
        assert not expired.cache_provenance.hit and transport.calls == 4

    asyncio.run(scenario())


def test_write_cache_policy_is_rejected_before_effect_or_operation_reservation(storage):
    async def scenario():
        platform, evidence, cache = storage
        tool, transport = definition("write"), Transport()
        gateway = ToolGateway(ToolCatalog((release(tool),)), transport, evidence, cache=cache)
        context = prepare(platform, "write", tool, ToolReadCachePolicy(ttl_seconds=10))
        result = await gateway.call(tool.tool_id, {"value": "one"}, context)
        assert result.code == "write_tool_cache_forbidden"
        assert transport.calls == 0
        assert await evidence.get_operation(context.operation_id) is None

    asyncio.run(scenario())


def test_shorter_request_ttl_cannot_extend_source_expiry_and_hits_are_not_republished(storage):
    async def scenario():
        platform, evidence, cache = storage
        tool, transport = definition(), Transport()
        gateway = ToolGateway(ToolCatalog((release(tool),)), transport, evidence, cache=cache)
        first = prepare(platform, "first", tool, ToolReadCachePolicy(ttl_seconds=60))
        original = await gateway.call(tool.tool_id, {"value": "one"}, first)
        second = prepare(platform, "second", tool, ToolReadCachePolicy(ttl_seconds=10))
        hit = await gateway.call(tool.tool_id, {"value": "one"}, second)
        assert hit.cache_provenance.expires_at == original.cache_provenance.fetched_at + timedelta(
            seconds=10
        )
        assert hit.cache_provenance.fetched_at == original.cache_provenance.fetched_at
        with pytest.raises(ValueError, match="policy or identity"):
            await cache.put(hit.cache_provenance.cache_key, second.operation_id)
        assert transport.calls == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("failure_mode", ["stopped", "release", "schema"])
def test_real_mcp_call_is_reused_only_after_confirmed_pg_cache_publication(storage, failure_mode):
    from app.domain.schema_contract import materialize_schema
    from app.infrastructure.mcp_transport import RELEASE_META, EmptySecretResolver, McpToolTransport

    async def scenario():
        platform, evidence, cache = storage
        tool = definition()
        frozen = release(tool)
        server = Server("cached-provider", version="v1")
        calls = []
        requests = []
        state = {"mode": "valid"}

        @server.list_tools()
        async def tools(request: types.ListToolsRequest):
            return types.ListToolsResult(
                tools=[
                    types.Tool(
                        name=tool.tool_id,
                        inputSchema=materialize_schema(
                            {**SCHEMA, "minProperties": 1} if state["mode"] == "schema" else SCHEMA
                        ),
                        outputSchema=materialize_schema(SCHEMA),
                    )
                ],
                _meta={
                    RELEASE_META: {
                        "pluginId": frozen.plugin_id,
                        "releaseId": frozen.release_id,
                        "artifactDigest": (
                            "sha256:" + "b" * 64
                            if state["mode"] == "release"
                            else frozen.artifact_digest
                        ),
                        "contractDigest": frozen.contract_digest,
                    }
                },
            )

        @server.call_tool()
        async def call_tool(name, arguments):
            calls.append(server.request_context.meta.model_dump(by_alias=True))
            return {"value": "mcp-output"}

        manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)

        async def application(scope, receive, send):
            requests.append(scope["method"])
            if state["mode"] == "stopped":
                await Response(status_code=503)(scope, receive, send)
            else:
                await manager.handle_request(scope, receive, send)

        async with manager.run():
            transport = McpToolTransport(
                EmptySecretResolver(), httpx.ASGITransport(app=application)
            )
            gateway = ToolGateway(ToolCatalog((frozen,)), transport, evidence, cache=cache)
            policy = ToolReadCachePolicy(ttl_seconds=30)
            first_context = prepare(platform, "first", tool, policy)
            first = await gateway.call(tool.tool_id, {"value": "input"}, first_context)
            second_context = prepare(platform, "second", tool, policy)
            second = await gateway.call(tool.tool_id, {"value": "input"}, second_context)
            state["mode"] = failure_mode
            previous_request_count = len(requests)
            assert await gateway.call(tool.tool_id, {"value": "input"}, first_context) == first
            assert await gateway.call(tool.tool_id, {"value": "input"}, second_context) == second
            assert len(requests) == previous_request_count
            rejected_context = prepare(platform, "unavailable", tool, policy)
            rejected = await gateway.call(tool.tool_id, {"value": "input"}, rejected_context)
            assert rejected.status == "failed" and rejected.code == "plugin_release_unavailable"
            assert rejected.output is None
            projected = platform.get_run("second")
            validation = next(item for item in projected.evidence if item.kind == "attempt")
            assert validation.metadata["networkKind"] == "cache_validation"
            assert validation.status == "succeeded"
            assert (await evidence.get_operation(second_context.operation_id)).result.output == {
                "value": "mcp-output"
            }
            with platform.session_factory() as session:
                row = session.get(ToolCacheRow, first.cache_provenance.cache_key)
                assert row.expires_at == first.cache_provenance.expires_at
        assert first.output == second.output == {"value": "mcp-output"}
        assert second.cache_provenance.hit and second.cache_provenance.source_run_id == "first"
        assert len(calls) == 1
        assert "cachePolicy" not in calls[0]["signaldeck/context"]

    asyncio.run(scenario())


def test_cache_storage_itself_rejects_successful_write_sources(storage):
    async def scenario():
        platform, evidence, cache = storage
        tool = definition("write")
        gateway = ToolGateway(ToolCatalog((release(tool),)), Transport(), evidence, cache=cache)
        context = prepare(platform, "write", tool)
        assert (
            await gateway.call(tool.tool_id, {"value": "effect"}, context)
        ).status == "succeeded"
        with pytest.raises(ValueError, match="confirmed read"):
            await cache.put("sha256:" + "a" * 64, context.operation_id)

    asyncio.run(scenario())


def test_scope_and_server_credential_revision_partition_read_cache(storage):
    async def scenario():
        platform, evidence, cache = storage
        tool, transport = definition(resources=("workspace",)), Transport()
        gateway = ToolGateway(ToolCatalog((release(tool),)), transport, evidence, cache=cache)
        policy = ToolReadCachePolicy(ttl_seconds=60)

        def binding(scope, revision):
            return {
                "workspace": {
                    "pluginId": tool.owner_plugin_id,
                    "scope": {"collection": scope},
                    "credentialRevision": revision,
                }
            }

        baseline = prepare(
            platform, "baseline", tool, policy, binding("research", "server-revision-one")
        )
        first = await gateway.call(tool.tool_id, {"value": "query"}, baseline)
        matching = prepare(
            platform, "matching", tool, policy, binding("research", "server-revision-one")
        )
        assert (await gateway.call(tool.tool_id, {"value": "query"}, matching)).cache_provenance.hit
        rotation = prepare(
            platform, "rotated", tool, policy, binding("research", "server-revision-two")
        )
        rotated = await gateway.call(tool.tool_id, {"value": "query"}, rotation)
        scoped = prepare(
            platform, "scoped", tool, policy, binding("private", "server-revision-two")
        )
        different_scope = await gateway.call(tool.tool_id, {"value": "query"}, scoped)
        assert not rotated.cache_provenance.hit and not different_scope.cache_provenance.hit
        assert (
            len(
                {
                    first.cache_provenance.cache_key,
                    rotated.cache_provenance.cache_key,
                    different_scope.cache_provenance.cache_key,
                }
            )
            == 3
        )
        assert transport.calls == 3
        missing_revision = prepare(
            platform,
            "missing-revision",
            tool,
            policy,
            {"workspace": {"pluginId": tool.owner_plugin_id, "scope": {"collection": "research"}}},
        )
        with pytest.raises(ValueError, match="credential revision"):
            await gateway.call(tool.tool_id, {"value": "query"}, missing_revision)
        assert transport.calls == 3

    asyncio.run(scenario())


def test_cache_publication_interruption_reuses_confirmed_operation_on_recovery(storage):
    async def scenario():
        platform, evidence, cache = storage
        tool, transport = definition(), Transport()

        class InterruptedCache:
            failed_once = False

            async def get(self, *args):
                return await cache.get(*args)

            async def put(self, *args):
                if not self.failed_once:
                    self.failed_once = True
                    raise RuntimeError("controlled publication interruption")
                await cache.put(*args)

        limiter = PostgresResourceLimiter(platform.session_factory)
        limiter.initialize()
        gateway = ToolGateway(
            ToolCatalog((release(tool),)),
            transport,
            evidence,
            limiter=limiter,
            cache=InterruptedCache(),
        )
        policy = ToolReadCachePolicy(ttl_seconds=60)
        context = prepare(platform, "interrupted", tool, policy)
        with pytest.raises(RuntimeError, match="publication interruption"):
            await gateway.call(tool.tool_id, {"value": "one"}, context)
        assert (await evidence.get_operation(context.operation_id)).status == "succeeded"
        recovered = await gateway.call(tool.tool_id, {"value": "one"}, context)
        assert recovered.status == "succeeded" and transport.calls == 1
        assert (
            await gateway.call(
                tool.tool_id, {"value": "one"}, prepare(platform, "later", tool, policy)
            )
        ).cache_provenance.hit
        assert transport.calls == 1

    asyncio.run(scenario())


def test_missing_cached_content_fails_explicitly_without_silent_fresh_substitution(storage):
    from app.infrastructure.artifact_store import ArtifactIntegrityError

    async def scenario():
        platform, evidence, cache = storage
        tool, transport = definition(), Transport()
        gateway = ToolGateway(ToolCatalog((release(tool),)), transport, evidence, cache=cache)
        policy = ToolReadCachePolicy(ttl_seconds=60)
        context = prepare(platform, "source", tool, policy)
        await gateway.call(tool.tool_id, {"value": "one"}, context)
        with platform.session_factory() as session:
            digest = session.get(OperationRow, context.operation_id).payload["result"]["output"][
                "$artifact"
            ]["digest"]
        content_hash = digest.removeprefix("sha256:")
        (cache.artifacts.root / content_hash[:2] / content_hash[2:]).unlink()
        with pytest.raises(ArtifactIntegrityError):
            await gateway.call(
                tool.tool_id, {"value": "one"}, prepare(platform, "later", tool, policy)
            )
        assert transport.calls == 1

    asyncio.run(scenario())


def test_cache_expiring_during_release_validation_fetches_fresh_without_extending_old_ttl(storage):
    async def scenario():
        platform, evidence, cache = storage
        tool = definition()
        policy = ToolReadCachePolicy(ttl_seconds=1)

        class SlowValidation(Transport):
            expiry = None

            async def verify_release(self, release, tool, context):
                await asyncio.sleep(
                    max(0, (self.expiry - datetime.now(UTC)).total_seconds()) + 0.01
                )
                return await super().verify_release(release, tool, context)

        transport = SlowValidation()
        gateway = ToolGateway(ToolCatalog((release(tool),)), transport, evidence, cache=cache)
        first_context = prepare(platform, "first", tool, policy)
        first = await gateway.call(tool.tool_id, {"value": "one"}, first_context)
        transport.expiry = first.cache_provenance.expires_at
        second_context = prepare(platform, "second", tool, policy)
        second = await gateway.call(tool.tool_id, {"value": "one"}, second_context)
        assert transport.calls == 2 and not second.cache_provenance.hit
        assert first.output != second.output
        assert second.cache_provenance.fetched_at > first.cache_provenance.expires_at
        assert (await evidence.get_operation(first_context.operation_id)).result == first
        projected = platform.get_run("second")
        attempts = [item for item in projected.evidence if item.kind == "attempt"]
        assert {item.metadata["networkKind"] for item in attempts} == {
            "cache_validation",
            "execute",
        }

    asyncio.run(scenario())

"""Unconfirmed write effects survive failures that only reject a later attempt."""

from __future__ import annotations

import asyncio

import pytest

from app.application.tool_gateway import ToolGateway
from app.domain.tool_contracts import ToolCatalog, ToolResult
from app.infrastructure.evidence_store import PostgresToolEvidenceStore
from app.infrastructure.platform_store import PlatformStore
from tests.test_platform_persistence import prepare_tree
from tests.test_tool_gateway_target import Transport, context, release, tool


@pytest.fixture()
def platform(session_factory):
    store = PlatformStore(session_factory)
    store.initialize()
    prepare_tree(store)
    return store


async def replay_after_response_loss(platform, first_outcome, failure_code, *, query=False):
    definition = tool("write", max_attempts=2)
    invocation = context(definition).model_copy(update={"node_id": "n", "invocation_id": "agent"})
    interrupted = (
        TimeoutError("response lost")
        if first_outcome == "timeout"
        else ToolResult(status="unknown", code="plugin_transport_interrupted")
    )
    rejected = ToolResult(status="failed", code=failure_code)
    transport = Transport([interrupted, rejected], query=ToolResult(status="not_found"))
    catalog = ToolCatalog(
        (
            release(
                definition,
                supports_operation_query=query,
                supports_operation_deduplication=True,
            ),
        )
    )
    gateway = ToolGateway(catalog, transport, PostgresToolEvidenceStore(platform.session_factory))
    result = await gateway.call(definition.tool_id, {"value": 1}, invocation)
    restarted = PostgresToolEvidenceStore(platform.session_factory)
    persisted = await restarted.get_operation(invocation.operation_id)
    assert persisted is not None
    assert persisted.context == invocation and persisted.effect == "write"
    assert persisted.arguments == {"value": 1}
    assert persisted.result == result
    assert await restarted.count_execute_attempts(invocation.operation_id) == 2
    assert transport.calls == 2 and transport.queries == int(query)

    evidence = platform.get_run(invocation.run_id).evidence
    operation = next(item for item in evidence if item.id == invocation.operation_id)
    attempts = sorted(
        (item for item in evidence if item.kind == "attempt"), key=lambda item: item.attempt
    )
    assert len(attempts) == persisted.attempts == 2 + int(query)
    assert all(
        item.operation_id == invocation.operation_id and item.parent_id == invocation.operation_id
        for item in attempts
    )
    assert [item.metadata["networkKind"] for item in attempts] == (
        ["execute", "query", "execute"] if query else ["execute", "execute"]
    )
    assert attempts[0].status == "unknown"
    assert attempts[-1].status == "failed" and attempts[-1].error_code == failure_code
    if query:
        assert attempts[1].metadata["resultStatus"] == "not_found"
    return result, persisted, operation, ToolGateway(catalog, transport, restarted), invocation


@pytest.mark.parametrize("first_outcome", ["timeout", "unknown"])
@pytest.mark.parametrize("failure_code", ["credential_unavailable", "plugin_release_unavailable"])
def test_deduplicated_write_replay_rejection_preserves_unknown(
    platform, first_outcome, failure_code
):
    async def scenario():
        result, persisted, operation, recovered, invocation = await replay_after_response_loss(
            platform, first_outcome, failure_code
        )
        # Permission to replay safely does not establish the outcome of the earlier write.
        assert result.status == "unknown"
        assert persisted.status == "unknown" and operation.status == "unknown"
        assert result.output is None
        replayed = await recovered.call(persisted.tool_id, {"value": 1}, invocation)
        assert replayed.status == "unknown"
        assert await recovered.evidence.count_execute_attempts(invocation.operation_id) == 2

    asyncio.run(scenario())


def test_confirmed_write_absence_allows_later_rejection_to_finish_failed(platform):
    async def scenario():
        result, persisted, operation, recovered, invocation = await replay_after_response_loss(
            platform, "timeout", "credential_unavailable", query=True
        )
        assert result.status == "failed" and result.code == "credential_unavailable"
        assert persisted.status == "failed" and operation.status == "failed"
        assert not result.retryable
        assert await recovered.call(persisted.tool_id, {"value": 1}, invocation) == result
        assert await recovered.evidence.count_execute_attempts(invocation.operation_id) == 2

    asyncio.run(scenario())

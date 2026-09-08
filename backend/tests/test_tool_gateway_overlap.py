"""Overlapping delivery must not duplicate a pending logical write operation."""

from __future__ import annotations

import asyncio

import pytest

from app.application.tool_gateway import ToolGateway
from app.domain.tool_contracts import ToolCatalog, ToolResult
from app.infrastructure.evidence_store import PostgresToolEvidenceStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.resource_limiter import PostgresResourceLimiter
from tests.test_platform_persistence import prepare_tree
from tests.test_tool_gateway_target import Transport, context, release, tool


class PendingWriteTransport(Transport):
    def __init__(self):
        super().__init__([])
        self.write_started = asyncio.Event()
        self.finish_first_write = asyncio.Event()
        self.effects = 0

    async def execute(self, release, tool, arguments, context):
        self.calls += 1
        if self.calls == 1:
            self.write_started.set()
            await self.finish_first_write.wait()
        self.effects += 1
        # Equal responses cannot disguise duplicate external effects in this test.
        return ToolResult(status="succeeded", output={"value": 1})

    async def query(self, release, tool, context):
        self.queries += 1
        if self.effects:
            return ToolResult(status="succeeded", output={"value": 1})
        # The first request is live but has not committed an observable effect yet.
        return ToolResult(status="not_found")


@pytest.mark.parametrize("max_attempts", [1, 2])
def test_overlapping_write_delivery_preserves_one_effect(session_factory, max_attempts):
    store = PlatformStore(session_factory)
    store.initialize()
    prepare_tree(store)
    limiter = PostgresResourceLimiter(session_factory)
    limiter.initialize()

    async def scenario():
        definition = tool(effect="write", max_attempts=max_attempts)
        invocation = context(definition).model_copy(
            update={"node_id": "n", "invocation_id": "agent"}
        )
        catalog = ToolCatalog((release(definition, supports_operation_query=True),))
        transport = PendingWriteTransport()
        first_evidence = PostgresToolEvidenceStore(session_factory)
        first_gateway = ToolGateway(catalog, transport, first_evidence, limiter=limiter)
        # Separate adapters represent a redelivery on another worker process.
        second_gateway = ToolGateway(
            catalog,
            transport,
            PostgresToolEvidenceStore(session_factory),
            limiter=PostgresResourceLimiter(session_factory),
        )
        first = asyncio.create_task(
            first_gateway.call(definition.tool_id, {"value": 1}, invocation)
        )
        second = None
        try:
            await asyncio.wait_for(transport.write_started.wait(), 5)
            second = asyncio.create_task(
                second_gateway.call(definition.tool_id, {"value": 1}, invocation)
            )
            overlapping_result = await asyncio.wait_for(asyncio.shield(second), 5)
            transport.finish_first_write.set()
            first_result = await asyncio.wait_for(first, 5)

            assert overlapping_result.status in {"unknown", "succeeded"}
            assert first_result.status == "succeeded"
            assert transport.calls == transport.effects == 1
            assert await first_evidence.count_execute_attempts(invocation.operation_id) == 1
            assert transport.calls <= max_attempts
            confirmed = await first_evidence.get_operation(invocation.operation_id)
            assert confirmed is not None and confirmed.status == "succeeded"
            assert confirmed.result == first_result
            replay = await second_gateway.call(definition.tool_id, {"value": 1}, invocation)
            assert replay == first_result
            assert transport.calls == transport.effects == 1
        finally:
            transport.finish_first_write.set()
            tasks = [task for task in (first, second) if task is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(scenario())

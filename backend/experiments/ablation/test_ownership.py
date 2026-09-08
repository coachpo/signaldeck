"""Measure logical write ownership under deterministic overlapping redelivery."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter

import pytest

from app.application.tool_gateway import ToolGateway
from app.domain.tool_contracts import ToolCatalog
from app.infrastructure.evidence_store import PostgresToolEvidenceStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.resource_limiter import PostgresResourceLimiter
from tests.test_platform_persistence import prepare_tree
from tests.test_tool_gateway_overlap import PendingWriteTransport
from tests.test_tool_gateway_target import context, release, tool


class UnownedEvidenceStore(PostgresToolEvidenceStore):
    """Remove only exclusive ownership; retain reservation and immutable evidence."""

    @asynccontextmanager
    async def operation_guard(self, operation_id, deadline):
        yield True


@pytest.mark.parametrize("scenario", ["normal", "overlap"])
def test_operation_ownership(session_factory, variant, sample, record, scenario):
    store = PlatformStore(session_factory)
    store.initialize()
    prepare_tree(store)
    limiter = PostgresResourceLimiter(session_factory)
    limiter.initialize()

    async def run():
        definition = tool(effect="write", max_attempts=2)
        invocation = context(definition).model_copy(
            update={"node_id": "n", "invocation_id": "agent"}
        )
        catalog = ToolCatalog((release(definition, supports_operation_query=True),))
        transport = PendingWriteTransport()
        evidence_type = UnownedEvidenceStore if variant == "ablated" else PostgresToolEvidenceStore
        evidence = evidence_type(session_factory)
        first_gateway = ToolGateway(catalog, transport, evidence, limiter=limiter)
        second_gateway = ToolGateway(
            catalog,
            transport,
            evidence_type(session_factory),
            limiter=PostgresResourceLimiter(session_factory),
        )
        started = perf_counter()
        first = asyncio.create_task(
            first_gateway.call(definition.tool_id, {"value": 1}, invocation)
        )
        second = None
        overlapping_result = None
        try:
            await asyncio.wait_for(transport.write_started.wait(), 5)
            if scenario == "overlap":
                second = asyncio.create_task(
                    second_gateway.call(definition.tool_id, {"value": 1}, invocation)
                )
                overlapping_result = await asyncio.wait_for(asyncio.shield(second), 5)
            transport.finish_first_write.set()
            first_result = await asyncio.wait_for(asyncio.shield(first), 5)
            replay_waits = 0
            while True:
                replay = await second_gateway.call(definition.tool_id, {"value": 1}, invocation)
                if replay.code != "operation_in_progress":
                    break
                remaining = (invocation.deadline - datetime.now(UTC)).total_seconds()
                assert remaining > 0, "Confirmed replay remained busy until the original deadline"
                replay_waits += 1
                # Match durable_worker.invoke's redelivery wait and original deadline.
                await asyncio.sleep(min(0.05, remaining))
            elapsed_ms = (perf_counter() - started) * 1000
            execute_attempts = await evidence.count_execute_attempts(invocation.operation_id)
            confirmed = await evidence.get_operation(invocation.operation_id)

            duplicate = variant == "ablated" and scenario == "overlap"
            expected_effects = 2 if duplicate else 1
            assert first_result.status == "succeeded"
            assert replay == first_result
            assert transport.calls == transport.effects == execute_attempts == expected_effects
            assert transport.queries == int(duplicate)
            assert transport.calls <= definition.max_attempts
            assert confirmed is not None and confirmed.status == "succeeded"
            assert confirmed.result == first_result
            if overlapping_result is not None:
                if duplicate:
                    assert overlapping_result == first_result
                else:
                    assert overlapping_result.status == "unknown"
                    assert overlapping_result.code == "operation_in_progress"

            record(
                {
                    "scenario": "ownership_" + scenario,
                    "mechanism": "operation_ownership",
                    "variant": variant,
                    "sample": sample,
                    "metrics": {
                        "calls": transport.calls,
                        "effects": transport.effects,
                        "queries": transport.queries,
                        "execute_attempts": execute_attempts,
                        "first_status": first_result.status,
                        "overlapping_status": (
                            overlapping_result.status if overlapping_result is not None else None
                        ),
                        "replay_status": replay.status,
                        "replay_waits": replay_waits,
                        "persisted_status": confirmed.status,
                        "elapsed_ms": elapsed_ms,
                    },
                }
            )
        finally:
            transport.finish_first_write.set()
            tasks = [task for task in (first, second) if task is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run())

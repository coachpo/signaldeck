"""Measure shared resource admission against a controlled two-slot service."""

from __future__ import annotations

import asyncio
import time

import pytest
from sqlalchemy import func, select

from app.application.tool_gateway import ToolGateway
from app.domain.tool_contracts import ToolCatalog, ToolResult
from app.infrastructure.evidence_store import PostgresToolEvidenceStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.resource_limiter import PostgresResourceLimiter, ResourcePermitRow
from tests.test_tool_cache import definition, prepare, release


class CapacityTransport:
    def __init__(self, first_wave):
        self.first_wave = first_wave
        self.started = asyncio.Event()
        self.release_work = asyncio.Event()
        self.active = 0
        self.peak = 0
        self.calls = 0
        self.rejected = 0

    async def execute(self, release, tool, arguments, context):
        self.active += 1
        self.calls += 1
        self.peak = max(self.peak, self.active)
        over_capacity = self.active > 2
        if self.active >= self.first_wave:
            self.started.set()
        try:
            await self.release_work.wait()
            await asyncio.sleep(0.04)
            if over_capacity:
                self.rejected += 1
                return ToolResult(status="failed", code="controlled_capacity_exceeded")
            return ToolResult(status="succeeded", output=dict(arguments))
        finally:
            self.active -= 1


@pytest.mark.parametrize("workload", ["within_capacity", "burst"])
def test_limiter(session_factory, variant, sample, workload, record):
    store = PlatformStore(session_factory)
    store.initialize()
    limiter = PostgresResourceLimiter(session_factory)
    limiter.initialize()

    async def scenario():
        count = 1 if workload == "within_capacity" else 8
        tool = definition(resources=("service",))
        bindings = {
            "service": {
                "pluginId": tool.owner_plugin_id,
                "maxConcurrentCalls": 2,
                "requestsPerSecond": 10000,
            }
        }
        contexts = [prepare(store, f"limit-{i}", tool, bindings=bindings) for i in range(count)]
        transport = CapacityTransport(min(count, 2) if variant == "baseline" else count)
        gateways = [
            ToolGateway(
                ToolCatalog((release(tool),)),
                transport,
                PostgresToolEvidenceStore(session_factory),
                limiter=PostgresResourceLimiter(session_factory) if variant == "baseline" else None,
            )
            for _ in range(2)
        ]
        started = time.perf_counter()
        tasks = [
            asyncio.create_task(gateways[i % 2].call(tool.tool_id, {"value": str(i)}, context))
            for i, context in enumerate(contexts)
        ]
        try:
            # Hold the admissible first wave until all its members have entered.
            # This establishes overlap deterministically; elapsed time is descriptive.
            await asyncio.wait_for(transport.started.wait(), 5)
            transport.release_work.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks), 10)
        finally:
            transport.release_work.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        elapsed_ms = (time.perf_counter() - started) * 1000
        with session_factory() as session:
            remaining = session.scalar(select(func.count()).select_from(ResourcePermitRow))
        successes = sum(result.status == "succeeded" for result in results)
        record(
            {
                "scenario": "limiter_" + workload,
                "mechanism": "resource_limiter",
                "variant": variant,
                "sample": sample,
                "metrics": {
                    "elapsed_ms": elapsed_ms,
                    "requests": count,
                    "successes": successes,
                    "tool_calls": transport.calls,
                    "peak_active": transport.peak,
                    "capacity_rejections": transport.rejected,
                    "remaining_permits": remaining,
                },
            }
        )
        expected_rejections = 6 if workload == "burst" and variant == "ablated" else 0
        assert transport.rejected == expected_rejections
        assert successes == count - expected_rejections
        assert transport.calls == count
        assert transport.peak == (min(count, 2) if variant == "baseline" else count)
        assert remaining == 0
        assert all(
            result.output == {"value": str(i)}
            for i, result in enumerate(results)
            if result.status == "succeeded"
        )

    asyncio.run(scenario())

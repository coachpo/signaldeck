"""Measure read-cache and retry contributions through the actual durable gateway."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.application.tool_gateway import ToolGateway
from app.domain.tool_contracts import ToolCatalog, ToolReadCachePolicy, ToolResult
from app.infrastructure.evidence_store import PostgresToolEvidenceStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.tool_cache_store import PostgresToolCacheStore
from tests.test_tool_cache import definition, prepare, release


class ControlledRead:
    """Stable output; separately count executions and mandatory release checks."""

    def __init__(self, transient=False):
        self.transient = transient
        self.calls = 0
        self.validations = 0

    async def execute(self, release, tool, arguments, context):
        self.calls += 1
        await asyncio.sleep(0.04)
        if self.transient and self.calls == 1:
            return ToolResult(status="failed", code="controlled_unavailable", retryable=True)
        return ToolResult(status="succeeded", output=dict(arguments))

    async def verify_release(self, release, tool, context):
        self.validations += 1
        await asyncio.sleep(0.005)
        return ToolResult(status="succeeded", output={"artifactDigest": release.artifact_digest})

    async def query(self, release, tool, context):
        raise AssertionError("Read workloads must not query write effects")


@pytest.mark.parametrize("workload", ["repeated", "unique"])
def test_cache(session_factory, variant, sample, workload, record):
    store = PlatformStore(session_factory)
    store.initialize()
    cache = PostgresToolCacheStore(session_factory)
    cache.initialize()

    async def scenario():
        tool = definition()
        transport = ControlledRead()
        gateway = ToolGateway(
            ToolCatalog((release(tool),)),
            transport,
            PostgresToolEvidenceStore(session_factory),
            cache=cache,
        )
        policy = ToolReadCachePolicy(ttl_seconds=60) if variant == "baseline" else None
        contexts = [prepare(store, f"cache-{index}", tool, policy) for index in range(8)]
        arguments = [
            {"value": "same" if workload == "repeated" else str(index)} for index in range(8)
        ]
        start = time.perf_counter()
        results = [
            await gateway.call(tool.tool_id, argument, context)
            for argument, context in zip(arguments, contexts, strict=True)
        ]
        elapsed_ms = (time.perf_counter() - start) * 1000
        hits = sum(
            bool(result.cache_provenance and result.cache_provenance.hit) for result in results
        )
        record(
            {
                "scenario": "cache_" + workload,
                "mechanism": "read_cache",
                "variant": variant,
                "sample": sample,
                "metrics": {
                    "elapsed_ms": elapsed_ms,
                    "requests": len(results),
                    "successes": sum(result.status == "succeeded" for result in results),
                    "tool_calls": transport.calls,
                    "release_checks": transport.validations,
                    "cache_hits": hits,
                    "outputs_correct": all(
                        result.output == argument
                        for result, argument in zip(results, arguments, strict=True)
                    ),
                },
            }
        )
        assert all(result.status == "succeeded" for result in results)
        assert [result.output for result in results] == arguments
        expected_hits = 7 if variant == "baseline" and workload == "repeated" else 0
        assert hits == transport.validations == expected_hits
        assert transport.calls == 8 - expected_hits
        if expected_hits:
            assert all(
                result.cache_provenance.source_run_id == contexts[0].run_id for result in results
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("workload", ["healthy", "transient", "persistent"])
def test_retry(session_factory, variant, sample, workload, record):
    store = PlatformStore(session_factory)
    store.initialize()

    async def scenario():
        tool = definition().model_copy(update={"max_attempts": 2 if variant == "baseline" else 1})

        class FaultRead(ControlledRead):
            async def execute(self, *args):
                result = await super().execute(*args)
                if workload == "persistent":
                    return ToolResult(
                        status="failed", code="controlled_unavailable", retryable=True
                    )
                return result

        transport = FaultRead(transient=workload == "transient")
        evidence = PostgresToolEvidenceStore(session_factory)
        gateway = ToolGateway(ToolCatalog((release(tool),)), transport, evidence)
        context = prepare(store, "retry", tool)
        start = time.perf_counter()
        result = await gateway.call(tool.tool_id, {"value": "stable"}, context)
        elapsed_ms = (time.perf_counter() - start) * 1000
        attempts = await evidence.count_execute_attempts(context.operation_id)
        record(
            {
                "scenario": "retry_" + workload,
                "mechanism": "read_retry",
                "variant": variant,
                "sample": sample,
                "metrics": {
                    "elapsed_ms": elapsed_ms,
                    "requests": 1,
                    "successes": int(result.status == "succeeded"),
                    "tool_calls": transport.calls,
                    "execute_attempts": attempts,
                    "result_status": result.status,
                },
            }
        )
        succeeds = workload == "healthy" or (workload == "transient" and variant == "baseline")
        assert (result.status == "succeeded") == succeeds
        assert (
            attempts
            == transport.calls
            == (2 if workload != "healthy" and variant == "baseline" else 1)
        )
        if succeeds:
            assert result.output == {"value": "stable"}

    asyncio.run(scenario())

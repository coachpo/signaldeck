"""Authorized tool operations with durable attempt evidence and effect-aware recovery."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol

from app.application.tool_cache import ToolCacheStore, fetched_result, read_cache_key
from app.domain.schema_contract import DomainValidationError, validate_value
from app.domain.tool_contracts import (
    PluginRelease,
    ToolCatalog,
    ToolDefinition,
    ToolInvocationContext,
    ToolOperationRecord,
    ToolResult,
    canonical_digest,
)


class ToolEvidenceStore(Protocol):
    def operation_guard(
        self, operation_id: str, deadline: datetime
    ) -> AbstractAsyncContextManager[bool]:
        """Yield exclusive logical-operation ownership; False must not write evidence."""
        ...

    async def get_operation(self, operation_id: str) -> ToolOperationRecord | None: ...

    async def count_execute_attempts(self, operation_id: str) -> int: ...

    async def reserve_operation(self, operation: ToolOperationRecord) -> bool:
        """Durably insert before I/O; return False on existing operation ID."""
        ...

    async def begin_attempt(self, operation_id: str, kind: str) -> int:
        """Durably allocate a network-attempt number before sending."""
        ...

    async def finish_attempt(self, operation_id: str, attempt: int, result: ToolResult) -> None: ...

    async def finish_operation(self, operation_id: str, result: ToolResult) -> None:
        """Persist result; reject any overwrite of a confirmed success."""
        ...


class ToolTransport(Protocol):
    async def execute(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        arguments: dict[str, Any],
        context: ToolInvocationContext,
    ) -> ToolResult: ...

    async def query(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        context: ToolInvocationContext,
    ) -> ToolResult: ...

    async def verify_release(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        context: ToolInvocationContext,
    ) -> ToolResult: ...


class ResourceLimiter(Protocol):
    def acquire(
        self,
        resources: dict[str, dict[str, Any]],
        operation_id: str,
        deadline: datetime,
    ) -> AbstractAsyncContextManager[None]: ...


class ToolGateway:
    def __init__(
        self,
        catalog: ToolCatalog,
        transport: ToolTransport,
        evidence: ToolEvidenceStore,
        limiter: ResourceLimiter | None = None,
        cache: ToolCacheStore | None = None,
    ):
        self.catalog = catalog
        self.transport = transport
        self.evidence = evidence
        self.limiter = limiter
        self.cache = cache

    async def call(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        context: ToolInvocationContext,
    ) -> ToolResult:
        if tool_id not in context.tool_grants:
            return ToolResult(status="failed", code="tool_not_granted")
        try:
            release, tool = self.catalog.binding(tool_id)
            validate_value(tool.input_schema, arguments, "$.arguments")
        except (ValueError, DomainValidationError):
            return ToolResult(status="failed", code="invalid_tool_input")
        if set(tool.resource_requirements) - set(context.resource_grants):
            return ToolResult(status="failed", code="resource_not_granted")
        if set(context.resource_bindings) - set(context.resource_grants):
            return ToolResult(status="failed", code="resource_binding_not_granted")
        for resource_id in tool.resource_requirements:
            binding = context.resource_bindings.get(resource_id)
            if binding is None or binding.get("pluginId") != tool.owner_plugin_id:
                return ToolResult(status="failed", code="resource_binding_unavailable")
        if context.cache_policy is not None and tool.effect != "read":
            return ToolResult(status="failed", code="write_tool_cache_forbidden")
        if context.cache_policy is not None and self.cache is None:
            return ToolResult(status="failed", code="tool_cache_unavailable")
        async with self.evidence.operation_guard(context.operation_id, context.deadline) as owned:
            if not owned:
                # A live owner may still commit an external effect or its result evidence.
                return ToolResult(status="unknown", code="operation_in_progress", retryable=True)
            return await self._call_owned(release, tool, arguments, context)

    async def _call_owned(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        arguments: dict[str, Any],
        context: ToolInvocationContext,
    ) -> ToolResult:
        tool_id = tool.tool_id
        proposed = ToolOperationRecord(
            context=context,
            tool_id=tool_id,
            input_digest=canonical_digest(arguments),
            effect=tool.effect,
            arguments=deepcopy(arguments),
        )
        fresh = await self.evidence.reserve_operation(proposed)
        previous = await self.evidence.get_operation(context.operation_id)
        if previous is None:
            raise RuntimeError("Operation reservation was not durable")
        if (
            previous.context != context
            or previous.tool_id != tool_id
            or previous.effect != tool.effect
            or previous.input_digest != proposed.input_digest
        ):
            return ToolResult(status="failed", code="operation_identity_conflict")
        if previous.status == "succeeded" and previous.result is not None:
            await self._publish_cache(previous.result)
            return previous.result
        if not fresh and previous.status == "failed" and previous.result is not None:
            if not previous.result.retryable:
                return previous.result
        if datetime.now(UTC) >= context.deadline:
            return await self._complete(
                context,
                ToolResult(
                    status="unknown" if not fresh and tool.effect == "write" else "failed",
                    code=(
                        "deadline_effect_unconfirmed"
                        if not fresh and tool.effect == "write"
                        else "deadline_exceeded"
                    ),
                ),
            )
        if self.cache is not None and context.cache_policy is not None:
            key = read_cache_key(release, tool, arguments, context)
            cached = await self.cache.get(key, context.cache_policy.ttl_seconds, context.run_id)
            if cached is not None:
                validate_value(tool.output_schema, cached.output, "$.cachedOutput")
                verified = await self._attempt(release, tool, {}, context, verify_only=True)
                if verified.status != "succeeded":
                    return await self._complete(context, verified)
                assert cached.cache_provenance is not None
                if cached.cache_provenance.expires_at > datetime.now(UTC):
                    return await self._complete(context, cached)
        absence_confirmed = False
        if not fresh and tool.effect == "write":
            recovered, absence_confirmed = await self._reconcile(release, tool, context)
            if recovered.status != "not_found":
                return await self._complete(context, recovered)
        execute_attempts = await self.evidence.count_execute_attempts(context.operation_id)
        return await self._execute(
            release,
            tool,
            arguments,
            context,
            execute_attempts,
            absence_confirmed,
            effect_unconfirmed=previous.status == "unknown" and not absence_confirmed,
        )

    async def _reconcile(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        context: ToolInvocationContext,
    ) -> tuple[ToolResult, bool]:
        if release.supports_operation_query:
            result = await self._attempt(release, tool, None, context)
            if result.status not in {"succeeded", "not_found"}:
                code = (
                    "deadline_effect_unconfirmed"
                    if datetime.now(UTC) >= context.deadline
                    else "effect_unconfirmed"
                )
                return ToolResult(status="unknown", code=code), False
            return result, result.status == "not_found"
        if release.supports_operation_deduplication:
            # Safe replay is not evidence that the earlier write had no effect.
            return ToolResult(status="not_found"), False
        return ToolResult(status="unknown", code="effect_unconfirmed"), False

    async def _execute(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        arguments: dict[str, Any],
        context: ToolInvocationContext,
        previous_execute_attempts: int,
        absence_confirmed: bool,
        *,
        effect_unconfirmed: bool,
    ) -> ToolResult:
        result = ToolResult(
            status="failed" if absence_confirmed else "unknown",
            code="effect_not_applied" if absence_confirmed else "attempt_limit_reached",
        )
        for execution_index in range(previous_execute_attempts, tool.max_attempts):
            result = await self._attempt(release, tool, arguments, context)
            if result.status == "succeeded":
                break
            if result.status == "failed" and tool.effect == "write" and effect_unconfirmed:
                # Rejecting this replay cannot establish the outcome of the earlier write.
                result = ToolResult(
                    status="unknown", code="effect_unconfirmed", retryable=result.retryable
                )
                if not result.retryable:
                    break
            if result.status == "unknown" and tool.effect == "write":
                effect_unconfirmed = True
                await self._complete(context, result)
                result, absence_confirmed = await self._reconcile(release, tool, context)
                if result.status != "not_found":
                    break
                effect_unconfirmed = not absence_confirmed
                result = ToolResult(
                    status="failed" if absence_confirmed else "unknown",
                    code="effect_not_applied" if absence_confirmed else "effect_unconfirmed",
                    retryable=execution_index + 1 < tool.max_attempts,
                )
            if not result.retryable or datetime.now(UTC) >= context.deadline:
                break
        await self._publish_cache(result)
        return await self._complete(context, result)

    async def _attempt(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        arguments: dict[str, Any] | None,
        context: ToolInvocationContext,
        *,
        verify_only: bool = False,
    ) -> ToolResult:
        if self.limiter is None:
            return await self._network_attempt(
                release, tool, arguments, context, verify_only=verify_only
            )
        resources = {ref: context.resource_bindings[ref] for ref in tool.resource_requirements}
        if not resources:
            resources = {"plugin:" + release.plugin_id: {}}
        try:
            async with self.limiter.acquire(resources, context.operation_id, context.deadline):
                return await self._network_attempt(
                    release, tool, arguments, context, verify_only=verify_only
                )
        except Exception:
            if verify_only:
                return ToolResult(status="failed", code="plugin_release_unavailable")
            return ToolResult(status="unknown", code="external_resource_interrupted")

    async def _network_attempt(
        self,
        release: PluginRelease,
        tool: ToolDefinition,
        arguments: dict[str, Any] | None,
        context: ToolInvocationContext,
        *,
        verify_only: bool = False,
    ) -> ToolResult:
        remaining = (context.deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            return ToolResult(status="failed", code="deadline_exceeded")
        attempt = await self.evidence.begin_attempt(
            context.operation_id,
            "cache_validation" if verify_only else "query" if arguments is None else "execute",
        )
        try:
            async with asyncio.timeout(min(tool.timeout_seconds, remaining)):
                if verify_only:
                    result = await self.transport.verify_release(release, tool, context)
                elif arguments is None:
                    result = await self.transport.query(release, tool, context)
                else:
                    result = await self.transport.execute(release, tool, arguments, context)
            result = result.model_copy(update={"cache_provenance": None})
            if verify_only and result.status != "succeeded":
                result = ToolResult(
                    status="failed", code=result.code or "plugin_release_unavailable"
                )
            if result.status == "succeeded" and not verify_only:
                try:
                    validate_value(tool.output_schema, result.output, "$.output")
                except DomainValidationError:
                    result = ToolResult(
                        status="unknown" if tool.effect == "write" else "failed",
                        code="invalid_tool_output",
                    )
            if (
                result.status == "succeeded"
                and context.cache_policy is not None
                and not verify_only
            ):
                assert arguments is not None
                key = read_cache_key(release, tool, arguments, context)
                result = fetched_result(result, key, context)
            if arguments is not None and result.status == "not_found":
                result = ToolResult(status="unknown", code="invalid_transport_result")
        except asyncio.CancelledError:
            result = ToolResult(
                status="failed" if verify_only else "unknown",
                code=(
                    "cache_validation_cancelled" if verify_only else "cancelled_effect_unconfirmed"
                ),
            )
            await asyncio.shield(
                self.evidence.finish_attempt(context.operation_id, attempt, result)
            )
            await asyncio.shield(self._complete(context, result))
            raise
        except Exception:
            # Transport exceptions can embed endpoint credentials or response contents.
            result = ToolResult(
                status="failed" if verify_only else "unknown",
                code="plugin_release_unavailable" if verify_only else "transport_interrupted",
                retryable=not verify_only,
            )
        await self.evidence.finish_attempt(context.operation_id, attempt, result)
        return result

    async def _complete(self, context: ToolInvocationContext, result: ToolResult) -> ToolResult:
        await self.evidence.finish_operation(context.operation_id, result)
        return result

    async def _publish_cache(self, result: ToolResult) -> None:
        provenance = result.cache_provenance
        if (
            self.cache is not None
            and result.status == "succeeded"
            and provenance is not None
            and not provenance.hit
        ):
            await self.cache.put(provenance.cache_key, provenance.source_operation_id)

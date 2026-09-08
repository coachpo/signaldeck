"""Explicit read-tool cache identity and provenance policy."""

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.domain.tool_contracts import (
    PluginRelease,
    ToolCacheProvenance,
    ToolDefinition,
    ToolInvocationContext,
    ToolResult,
    canonical_digest,
)


class ToolCacheStore(Protocol):
    async def get(
        self, key: str, ttl_seconds: int, requesting_run_id: str
    ) -> ToolResult | None: ...

    async def put(self, key: str, source_operation_id: str) -> None:
        """Publish only an immutable, confirmed, explicitly cached read operation."""
        ...


def read_cache_key(
    release: PluginRelease,
    tool: ToolDefinition,
    arguments: dict[str, Any],
    context: ToolInvocationContext,
) -> str:
    if context.cache_policy is None or tool.effect != "read":
        raise ValueError("Only explicitly selected read tools can use result caching")
    resources = {}
    for resource_id in tool.resource_requirements:
        binding = context.resource_bindings[resource_id]
        revision = binding.get("credentialRevision")
        if not isinstance(revision, str) or not revision:
            raise ValueError("Read cache requires a resolved credential revision")
        resources[resource_id] = {
            "pluginId": binding["pluginId"],
            "scope": binding["scope"],
            "credentialRevision": revision,
        }
    return canonical_digest(
        {
            "version": "signaldeck.read-tool-cache/1",
            "toolId": tool.tool_id,
            "releaseId": release.release_id,
            "artifactDigest": release.artifact_digest,
            "contractDigest": release.contract_digest,
            "endpoint": release.endpoint,
            "protocolVersion": release.protocol_version,
            "input": arguments,
            "resources": resources,
        }
    )


def fetched_result(result: ToolResult, key: str, context: ToolInvocationContext) -> ToolResult:
    assert context.cache_policy is not None
    fetched_at = datetime.now(UTC)
    return result.model_copy(
        update={
            "cache_provenance": ToolCacheProvenance(
                hit=False,
                source_run_id=context.run_id,
                source_operation_id=context.operation_id,
                fetched_at=fetched_at,
                expires_at=fetched_at + timedelta(seconds=context.cache_policy.ttl_seconds),
                cache_key=key,
            )
        }
    )

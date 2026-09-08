"""Explicit execution adapters bound once in the worker composition root."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.application.tool_gateway import ToolTransport
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_ports import BoundCredentialReader


@dataclass(frozen=True)
class TemporalServices:
    """Worker composition arguments; never passed into workflow or activity execution."""

    store: PlatformStore
    artifacts: ArtifactStore
    transport: Callable[[dict[str, Any]], ToolTransport]
    core_artifact: str
    verify_core: Callable[[], None]


class FrozenSecretResolver:
    """Resolve only a frozen resource owner and the references required by one I/O."""

    def __init__(self, credentials: BoundCredentialReader, bindings: dict[str, Any]):
        self.credentials, self.bindings = credentials, bindings

    async def resolve(self, plugin_id: str, resource_refs: tuple[str, ...]) -> dict[str, str]:
        import asyncio

        headers: dict[str, str] = {}
        for resource_id in resource_refs:
            binding = self.bindings["resourceBindings"].get(resource_id)
            if binding is None or binding.get("pluginId") != plugin_id:
                raise ValueError("Frozen resource owner mismatch")
            revision = binding.get("credentialRevision")
            if not isinstance(revision, str) or not revision:
                raise ValueError("Frozen credential reference is unavailable")
            values = await asyncio.to_thread(self.credentials, resource_id, revision)
            for key, value in values.items():
                if not isinstance(value, str) or key.lower().startswith("mcp-"):
                    raise ValueError("Invalid credential header")
                if key in headers and headers[key] != value:
                    raise ValueError("Credential header conflict")
                headers[key] = value
        return headers

"""Frozen tool identities and execution-boundary value contracts."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from typing import Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.domain.resources import (
    ResolvedToolResourceConfiguration,
    ToolResourceConfiguration,
    reject_credential_fields,
)
from app.domain.schema_contract import materialize_schema, validate_schema
from app.schemas.common import CamelModel

MCP_PROTOCOL_VERSION: Literal["2025-11-25"] = "2025-11-25"
QUALIFIED_ID = r"^[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.-]*/[a-zA-Z0-9][a-zA-Z0-9_.-]*$"
PLUGIN_ID = r"^[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.-]*$"
DIGEST = r"^sha256:[a-f0-9]{64}$"


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class ToolContractModel(CamelModel):
    model_config = ConfigDict(frozen=True, validate_default=True)


class ToolDefinition(ToolContractModel):
    tool_id: str = Field(pattern=QUALIFIED_ID)
    owner_plugin_id: str = Field(pattern=PLUGIN_ID)
    description: str = ""
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    effect: Literal["read", "write"] = "read"
    resource_requirements: tuple[str, ...] = ()
    timeout_seconds: float = Field(default=30.0, gt=0, le=3600)
    max_attempts: int = Field(default=1, ge=1, le=10)

    @field_validator("input_schema", "output_schema")
    @classmethod
    def supported_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_schema(value)
        return copy.deepcopy(value)

    @model_validator(mode="after")
    def owned_identity(self) -> Self:
        if self.tool_id.rsplit("/", 1)[0] != self.owner_plugin_id:
            raise ValueError("Tool identity must be qualified by its owner")
        if self.input_schema["type"] != "object":
            raise ValueError("Tool input must be an object for the pinned MCP protocol")
        if self.output_schema["type"] != "object":
            raise ValueError("Tool output must be an object for MCP structuredContent")
        return self


class PluginRelease(ToolContractModel):
    plugin_id: str = Field(pattern=PLUGIN_ID)
    release_id: str = Field(min_length=1)
    artifact_digest: str = Field(pattern=DIGEST)
    endpoint: str
    page_url: str | None = None
    protocol_version: Literal["2025-11-25"] = MCP_PROTOCOL_VERSION
    config_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    tools: tuple[ToolDefinition, ...]
    contract_digest: str = Field(pattern=DIGEST)
    supports_operation_query: bool = False
    supports_operation_deduplication: bool = False

    @field_validator("endpoint")
    @classmethod
    def safe_endpoint(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError("Plugin endpoint must be an HTTP URL without credentials or query")
        return value

    @field_validator("page_url")
    @classmethod
    def safe_page_url(cls, value: str | None) -> str | None:
        return cls.safe_endpoint(value) if value is not None else None

    @model_validator(mode="after")
    def verified_contract(self) -> Self:
        validate_schema(self.config_schema)
        if any(tool.owner_plugin_id != self.plugin_id for tool in self.tools):
            raise ValueError("Release tools must belong to its plugin")
        if len({tool.tool_id for tool in self.tools}) != len(self.tools):
            raise ValueError("Duplicate tool identity")
        if self.contract_digest != tool_contract_digest(self.tools):
            raise ValueError("Tool contract digest mismatch")
        return self


def tool_contract_digest(tools: tuple[ToolDefinition, ...]) -> str:
    return canonical_digest(
        [
            tool.model_dump(mode="json", by_alias=True)
            for tool in sorted(tools, key=lambda item: item.tool_id)
        ]
    )


class ToolReadCachePolicy(ToolContractModel):
    ttl_seconds: int = Field(ge=1, le=86400)
    scope: Literal["resource"] = "resource"
    key: Literal["release_input_resources"] = "release_input_resources"


class ToolCacheProvenance(ToolContractModel):
    hit: bool
    source_run_id: str
    source_operation_id: str
    fetched_at: datetime
    expires_at: datetime
    cache_key: str = Field(pattern=DIGEST)


class ToolInvocationContext(ToolContractModel):
    run_id: str
    node_id: str
    invocation_id: str
    operation_id: str
    deadline: datetime
    tool_grants: tuple[str, ...]
    resource_grants: tuple[str, ...] = ()
    resource_bindings: dict[str, dict[str, Any]] = Field(default_factory=dict)
    cache_policy: ToolReadCachePolicy | None = None

    @field_validator("resource_bindings")
    @classmethod
    def non_sensitive_bindings(cls, value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result = {}
        for resource_id, config in value.items():
            reject_credential_fields(config)
            schema = (
                ResolvedToolResourceConfiguration
                if "credentialRevision" in config
                else ToolResourceConfiguration
            )
            result[resource_id] = schema.model_validate(config).model_dump(
                mode="json", by_alias=True
            )
        return result

    @field_validator("deadline")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Deadline requires timezone")
        return value


class ToolResult(ToolContractModel):
    status: Literal["succeeded", "failed", "unknown", "not_found"]
    output: Any = None
    code: str | None = None
    retryable: bool = False
    cache_provenance: ToolCacheProvenance | None = None


class ToolOperationRecord(ToolContractModel):
    context: ToolInvocationContext
    tool_id: str
    input_digest: str
    effect: Literal["read", "write"] = "write"
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "succeeded", "failed", "unknown"] = "pending"
    result: ToolResult | None = None
    attempts: int = 0


class ArtifactRef(ToolContractModel):
    digest: str = Field(pattern=DIGEST)
    size_bytes: int = Field(ge=0)
    media_type: str = "application/octet-stream"


class ToolCatalog:
    """A run-local copy; declarations and dispatch share this frozen contract."""

    def __init__(self, releases: tuple[PluginRelease, ...]):
        self._bindings: dict[str, tuple[PluginRelease, ToolDefinition]] = {}
        for release in releases:
            frozen = PluginRelease.model_validate_json(release.model_dump_json())
            for tool in frozen.tools:
                if tool.tool_id in self._bindings:
                    raise ValueError("Conflicting frozen tool identity")
                self._bindings[tool.tool_id] = (frozen, tool)
        self._aliases = {
            "tool_" + hashlib.sha256(tool_id.encode()).hexdigest()[:59]: tool_id
            for tool_id in sorted(self._bindings)
        }
        if len(self._aliases) != len(self._bindings):
            raise ValueError("Tool alias collision")

    def binding(self, tool_id: str) -> tuple[PluginRelease, ToolDefinition]:
        if tool_id not in self._bindings:
            raise ValueError("Unknown frozen tool")
        release, tool = self._bindings[tool_id]
        return release.model_copy(deep=True), tool.model_copy(deep=True)

    def resolve_alias(self, alias: str) -> str:
        if alias not in self._aliases:
            raise ValueError("Unknown frozen tool alias")
        return self._aliases[alias]

    def model_tools(self, grants: tuple[str, ...]) -> list[dict[str, Any]]:
        if set(grants) - self._bindings.keys():
            raise ValueError("Grant references unknown frozen tool")
        return [
            {
                "name": alias,
                "description": self._bindings[tool_id][1].description,
                "parameters": materialize_schema(self._bindings[tool_id][1].input_schema),
            }
            for alias, tool_id in self._aliases.items()
            if tool_id in grants
        ]

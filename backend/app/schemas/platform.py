"""HTTP contracts for definitions, resources, plugins and launch actions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, JsonValue

from app.domain.definitions import PackageDefinition, WorkflowPlan
from app.domain.plugin_catalog import PluginObservation
from app.domain.tool_contracts import PluginRelease
from app.schemas.common import CamelModel


class ManifestRequest(CamelModel):
    manifest_source: str = Field(min_length=1, max_length=262144)


class DiagnosticRead(CamelModel):
    code: str
    path: str
    message: str
    line: int | None = None
    column: int | None = None


class ValidationRead(CamelModel):
    definition: PackageDefinition | None = None
    plans: dict[str, WorkflowPlan] | None = None
    content_hash: str | None = None
    diagnostics: list[DiagnosticRead] = Field(default_factory=list)


class PackageRead(CamelModel):
    id: str
    key: str
    name: str
    description: str
    source: str
    definition: PackageDefinition
    plans: dict[str, WorkflowPlan]
    package_hash: str
    created_at: datetime
    updated_at: datetime


class PackageList(CamelModel):
    items: list[PackageRead]


class LaunchRequest(CamelModel):
    workflow_key: str = Field(min_length=1, max_length=120)
    parameters: JsonValue = Field(default_factory=dict)
    launch_id: str | None = Field(default=None, min_length=1, max_length=200)


class RerunRequest(CamelModel):
    launch_id: str | None = Field(default=None, min_length=1, max_length=200)


class PluginWrite(CamelModel):
    release: PluginRelease
    enabled: bool = True


class PluginEnabled(CamelModel):
    enabled: bool


class PluginRead(CamelModel):
    plugin_id: str
    enabled: bool
    release: dict[str, Any]
    health: PluginObservation = Field(default_factory=PluginObservation)


class PluginList(CamelModel):
    items: list[PluginRead]

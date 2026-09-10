"""Safe task preparation and historical result response contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, JsonValue

from app.domain.definitions import WorkflowDefinition
from app.domain.execution import LaunchOrigin, RunStatus
from app.domain.model_diagnostics import ModelErrorCategory, ModelObservation
from app.schemas.common import CamelModel


class PrepareRequest(CamelModel):
    workflow_key: str = Field(min_length=1, max_length=120)
    parameters: JsonValue = Field(default_factory=dict)
    revision_hash: str | None = None
    source_run_id: str | None = None


class PreparationRequirement(CamelModel):
    model_observation: ModelObservation | None = None
    id: str
    kind: Literal["model", "tool", "plugin"]
    name: str
    configured: bool
    has_credentials: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    observation: Literal["not_observed", "succeeded", "failed", "unknown"] = "not_observed"
    observed_at: datetime | None = None
    observation_error: str | None = None
    issue: str | None = None


class PreparationRead(CamelModel):
    package_key: str
    workflow_key: str
    package_hash: str
    ready: bool
    binding_token: str | None = None
    requirements: list[PreparationRequirement] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    changed_bindings: list[str] = Field(default_factory=list)
    previous_bindings: dict[str, JsonValue] = Field(default_factory=dict)
    effective_settings: dict[str, JsonValue] = Field(default_factory=dict)


class ReuseRead(CamelModel):
    source_run_id: str
    package_key: str
    workflow_key: str
    package_hash: str
    parameters: JsonValue
    input_schema: dict[str, Any]
    workflow: WorkflowDefinition


class ReuseRequest(CamelModel):
    parameters: JsonValue
    launch_id: str = Field(min_length=1, max_length=200)
    binding_token: str | None = None


class ResultAttachment(CamelModel):
    kind: Literal["artifact"]
    label: str
    reference: JsonValue
    node_id: str | None = None
    operation_id: str | None = None
    tool_evidence_id: str | None = None
    evidence_id: str | None = None
    plugin_id: str | None = None


class ResultSection(CamelModel):
    kind: Literal["markdown", "value", "receipt", "sources", "dataTime", "notice", "link"]
    label: str
    value: JsonValue = None
    evidence_id: str | None = None
    node_id: str | None = None
    operation_id: str | None = None
    tool_evidence_id: str | None = None
    plugin_id: str | None = None
    href: str | None = None
    severity: Literal["info", "warning", "missing"] | None = None


class ResultRead(CamelModel):
    error_category: ModelErrorCategory | None = None
    run_id: str
    title: str
    status: RunStatus
    content_status: Literal["not_available", "available", "partial", "unknown"]
    sections: list[ResultSection] = Field(default_factory=list)
    deferred_sections: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    execution_issues: list[str] = Field(default_factory=list)
    body: str | None = None
    receipt: JsonValue = None
    data_time: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    origin: LaunchOrigin
    sources: list[JsonValue] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    attachments: list[ResultAttachment] = Field(default_factory=list)
    unknown_evidence_ids: list[str] = Field(default_factory=list)
    freshness: list[JsonValue] = Field(default_factory=list)
    error_code: str | None = None

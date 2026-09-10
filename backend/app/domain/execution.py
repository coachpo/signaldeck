"""Persisted execution identities exchanged across application boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, JsonValue

from app.schemas.common import CamelModel

type RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
type EvidenceStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "failed",
    "blocked",
    "skipped",
    "cancelled",
    "timed_out",
    "unknown",
]
type EvidenceKind = Literal["node", "agent", "model", "tool", "attempt"]


class LaunchOrigin(CamelModel):
    kind: Literal["manual", "rerun", "reuse", "schedule"] = "manual"
    source_run_id: str | None = None
    schedule_id: str | None = None
    trigger_id: str | None = None
    scheduled_at: datetime | None = None


class ResolvedRunSpec(CamelModel):
    run_id: str
    package_key: str
    workflow_key: str
    package_hash: str
    definition: dict[str, JsonValue]
    plan: dict[str, JsonValue]
    parameters: JsonValue
    model_bindings: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
    plugin_releases: list[dict[str, JsonValue]] = Field(default_factory=list)
    resource_bindings: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
    tool_aliases: dict[str, str] = Field(default_factory=dict)
    core_artifact: str
    deadline: datetime
    origin: LaunchOrigin = Field(default_factory=LaunchOrigin)


class RunSummary(CamelModel):
    title: str = ""
    has_unknown_effects: bool = False
    has_unknown_results: bool = False
    id: str
    package_key: str
    workflow_key: str
    package_hash: str
    status: RunStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    origin: LaunchOrigin


class ExecutionEvidence(CamelModel):
    id: str
    run_id: str
    parent_id: str | None = None
    node_id: str
    kind: EvidenceKind
    status: EvidenceStatus
    attempt: int = Field(default=1, ge=1)
    operation_id: str | None = None
    tool_id: str | None = None
    input: JsonValue = None
    output: JsonValue = None
    error_code: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class RunDetail(RunSummary):
    spec: ResolvedRunSpec
    output: JsonValue = None
    error_code: str | None = None
    evidence: list[ExecutionEvidence] = Field(default_factory=list)


class StartCommand(CamelModel):
    id: str
    run_id: str
    kind: Literal["start", "cancel"]
    attempts: int = 0
    created_at: datetime


class ApplicationError(Exception):
    """A stable public failure code without infrastructure exception text."""

    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

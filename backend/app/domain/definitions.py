"""Workflow Package definitions shared by YAML, editor, compiler and runtime."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator

from app.domain.mappings import validate_condition, validate_mapping
from app.domain.presentation import WorkflowPresentation
from app.domain.schema_contract import validate_schema
from app.domain.tool_contracts import QUALIFIED_ID, ToolReadCachePolicy
from app.schemas.common import CamelModel

Key = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,119}$")]
ToolId = Annotated[str, Field(pattern=QUALIFIED_ID)]
TerminalState = Literal["succeeded", "failed", "skipped", "blocked", "cancelled", "timed_out"]


class Budget(CamelModel):
    max_model_requests: int = Field(default=12, ge=1, le=1000)
    max_tool_calls: int = Field(default=32, ge=1, le=10000)
    max_tokens: int = Field(default=100000, ge=1)
    deadline_seconds: int = Field(default=300, ge=1, le=86400)
    max_parallel_tools: int = Field(default=4, ge=1, le=128)


class ModelStrategy(CamelModel):
    kind: Literal["model"]
    model_ref: Key
    prompt: str = Field(min_length=1, max_length=100000)


class DeterministicStrategy(CamelModel):
    kind: Literal["deterministic"]
    tool_id: ToolId
    input_mapping: dict[str, Any] = Field(default_factory=lambda: {"ref": "agent.input"})
    output_mapping: dict[str, Any] = Field(default_factory=lambda: {"ref": "tool.output"})

    @field_validator("input_mapping", "output_mapping")
    @classmethod
    def check_mapping(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_mapping(value)
        return value


class AgentDefinition(CamelModel):
    name: str = Field(default="", max_length=200)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    strategy: Annotated[ModelStrategy | DeterministicStrategy, Field(discriminator="kind")]
    tools: list[ToolId] = Field(default_factory=list)
    resources: list[Key] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    tool_cache: dict[ToolId, ToolReadCachePolicy] = Field(default_factory=dict)

    @field_validator("input_schema", "output_schema")
    @classmethod
    def check_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_schema(value)
        return value

    @model_validator(mode="after")
    def check_tool_grant(self) -> AgentDefinition:
        if set(self.tool_cache) - set(self.tools):
            raise ValueError("Cache policies require an Agent tool grant")
        if (
            isinstance(self.strategy, DeterministicStrategy)
            and self.strategy.tool_id not in self.tools
        ):
            raise ValueError("Deterministic tool must be included in Agent tools")
        return self


class NodeDefinition(CamelModel):
    uses: Key
    depends_on: list[Key] = Field(default_factory=list)
    input_mapping: dict[str, Any]
    condition: dict[str, Any] | None = None
    accept_upstream_states: list[TerminalState] = Field(default=["succeeded"])
    max_attempts: int = Field(default=1, ge=1, le=10)

    @field_validator("input_mapping")
    @classmethod
    def check_mapping(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_mapping(value)
        return value

    @field_validator("condition")
    @classmethod
    def check_condition(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            validate_condition(value)
        return value

    @field_validator("accept_upstream_states")
    @classmethod
    def check_states(cls, value: list[TerminalState]) -> list[TerminalState]:
        if not value or len(set(value)) != len(value):
            raise ValueError("Accepted upstream states must be nonempty and unique")
        return value


class WorkflowDefinition(CamelModel):
    description: str | None = Field(default=None, max_length=10000, exclude_if=lambda v: v is None)
    presentation: WorkflowPresentation | None = Field(default=None, exclude_if=lambda v: v is None)

    @field_validator("presentation", "description", mode="before")
    @classmethod
    def check_presentation_present(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Optional Workflow fields must be omitted rather than null")
        return value

    name: str = Field(default="", max_length=200)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    nodes: dict[Key, NodeDefinition] = Field(min_length=1, max_length=1000)
    output_mapping: dict[str, Any]
    max_parallel_nodes: int = Field(default=8, ge=1, le=128)
    deadline_seconds: int = Field(default=3600, ge=1, le=604800)
    failure_policy: Literal["continue_independent", "fail_fast"] = "continue_independent"

    @field_validator("input_schema", "output_schema")
    @classmethod
    def check_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_schema(value)
        return value

    @field_validator("output_mapping")
    @classmethod
    def check_mapping(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_mapping(value)
        return value


class PackageMetadata(CamelModel):
    key: Key
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)


class PackageDefinition(CamelModel):
    api_version: Literal["signaldeck.workflowPackage/v2"] = "signaldeck.workflowPackage/v2"
    metadata: PackageMetadata
    agents: dict[Key, AgentDefinition] = Field(min_length=1, max_length=1000)
    workflows: dict[Key, WorkflowDefinition] = Field(min_length=1, max_length=1000)


class DependencyEdge(CamelModel):
    source: str
    target: str
    sources: list[Literal["control", "input", "condition"]]
    paths: list[str]


class WorkflowPlan(CamelModel):
    workflow_key: str
    node_order: list[str]
    dependencies: dict[str, list[str]]
    edges: list[DependencyEdge]


class CompiledPackage(CamelModel):
    package: PackageDefinition
    plans: dict[str, WorkflowPlan]
    content_hash: str

"""Explicit editor drafts: unfinished text is distinct from applied JSON."""

from datetime import datetime
from typing import Self

from pydantic import Field, JsonValue, model_validator

from app.domain.definitions import WorkflowDefinition
from app.schemas.common import CamelModel


class TaskDraftWrite(CamelModel):
    revision: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=160)
    package_key: str
    workflow_key: str
    package_hash: str
    source_run_id: str | None = None
    has_parameters: bool = True
    parameters: JsonValue = None
    json_text: str | None = Field(default=None, max_length=1000000)
    launch_id: str = Field(min_length=1, max_length=200)
    pending: bool = False
    binding_token: str | None = None

    @model_validator(mode="after")
    def consistent_state(self) -> Self:
        if not self.has_parameters and self.parameters is not None:
            raise ValueError("Absent parameters cannot contain a value")
        if self.pending and (not self.binding_token or self.json_text is not None):
            raise ValueError("Pending launch requires applied inputs and reviewed bindings")
        if not self.pending and self.binding_token is not None:
            raise ValueError("Only pending launches retain binding tokens")
        return self


class TaskDraftRead(TaskDraftWrite):
    id: str
    updated_at: datetime
    current_package_hash: str | None
    needs_revalidation: bool
    workflow: WorkflowDefinition


class TaskDraftList(CamelModel):
    items: list[TaskDraftRead]

"""Optional input presets and task bookmarks; these are never execution roots."""

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import Field, JsonValue, model_validator

from app.schemas.common import CamelModel


class TaskPresetInput(CamelModel):
    parameters: JsonValue = None
    has_parameters: bool = False

    @model_validator(mode="before")
    @classmethod
    def infer_legacy_presence(cls, value: Any) -> Any:
        if isinstance(value, dict) and not ({"hasParameters", "has_parameters"} & value.keys()):
            return {**value, "hasParameters": value.get("parameters") is not None}
        return value

    @model_validator(mode="after")
    def consistent_presence(self) -> Self:
        if not self.has_parameters and self.parameters is not None:
            raise ValueError("A bookmark cannot include saved inputs")
        return self


class TaskPresetCreate(TaskPresetInput):
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")
    package_key: str = Field(min_length=1)
    workflow_key: str = Field(min_length=1)
    package_hash: str = Field(min_length=1)
    is_favorite: bool = False
    is_pinned: bool = False


class TaskPresetUpdate(TaskPresetInput):
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")
    package_hash: str = Field(min_length=1)
    is_favorite: bool = False
    is_pinned: bool = False


class PresetDiagnostic(CamelModel):
    code: str
    path: str
    message: str


class TaskPresetRead(TaskPresetCreate):
    id: str
    created_at: datetime
    updated_at: datetime
    current_package_hash: str | None
    needs_revalidation: bool
    validation_status: Literal["valid", "invalid", "unavailable", "not_applicable"]
    validation_errors: list[PresetDiagnostic] = Field(default_factory=list)


class TaskPresetList(CamelModel):
    items: list[TaskPresetRead]

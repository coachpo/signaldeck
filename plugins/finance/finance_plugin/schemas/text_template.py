from __future__ import annotations

from datetime import datetime

from plugin_runtime.common import CamelModel, normalize_runtime_inputs
from pydantic import Field, field_validator, model_validator


class TextTemplateCreate(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name is required")
        return normalized

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content is required")
        return value


class TextTemplateUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    content: str | None = Field(default=None, min_length=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name is required")
        return normalized

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("Content is required")
        return value

    @model_validator(mode="after")
    def validate_payload(self) -> TextTemplateUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Name is required")
        if "content" in self.model_fields_set and self.content is None:
            raise ValueError("Content is required")
        return self


class TextTemplateRead(CamelModel):
    id: int
    name: str
    content: str
    created_at: datetime
    updated_at: datetime


class TextTemplateCompileRead(CamelModel):
    id: int
    name: str
    compiled: str


class TextTemplateCompileInputs(CamelModel):
    inputs: dict[str, str] = Field(default_factory=dict)

    @field_validator("inputs", mode="before")
    @classmethod
    def validate_inputs(cls, value: object) -> dict[str, str]:
        return normalize_runtime_inputs(value)


class TextTemplateInlineCompile(TextTemplateCompileInputs):
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content is required")
        return value


class TextTemplateInlineCompileRead(CamelModel):
    compiled: str


class TextTemplateStoredCompile(TextTemplateCompileInputs):
    pass


class PlaceholderReportRead(CamelModel):
    name: str
    label: str
    created_at: datetime


class PlaceholderTreeRead(CamelModel):
    reports: list[PlaceholderReportRead]

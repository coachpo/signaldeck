from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal, cast

from plugin_runtime.common import CamelModel, normalize_runtime_inputs, to_camel
from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

ReportSource = Literal["compiled", "uploaded", "external", "agent"]
REPORT_SOURCE_VALUES: tuple[ReportSource, ...] = (
    "compiled",
    "uploaded",
    "external",
    "agent",
)


class ReportAnalysisMetadata(CamelModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
        extra="forbid",
    )

    ticker: str | None = None
    review_type: str | None = None
    trigger: str | None = None
    review_date: str | None = None
    version_group: str | None = None

    @field_validator(
        "ticker",
        "review_type",
        "trigger",
        "review_date",
        "version_group",
    )
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.upper()


class ReportCreatedByMetadata(CamelModel):
    type: Literal["agent"]
    run_id: str
    node_id: str
    invocation_id: str
    operation_id: str


class ReportMetadata(CamelModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
        extra="forbid",
    )

    author: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    analysis: ReportAnalysisMetadata | None = None

    @field_validator("author", "description")
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized_tags: list[str] = []
        for tag in value:
            trimmed = tag.strip()
            if trimmed:
                normalized_tags.append(trimmed)
        return normalized_tags


class ReportReadMetadata(ReportMetadata):
    created_by: ReportCreatedByMetadata | None = None


class ReportCompileCreate(CamelModel):
    metadata: ReportMetadata = Field(default_factory=ReportMetadata)
    inputs: dict[str, str] = Field(default_factory=dict)

    @field_validator("inputs", mode="before")
    @classmethod
    def validate_inputs(cls, value: object) -> dict[str, str]:
        return normalize_runtime_inputs(value)


class ReportCreate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=200)
    source: Literal["external"] = "external"
    content: str = Field(min_length=1)
    metadata: ReportMetadata = Field(default_factory=ReportMetadata)

    @field_validator("name", "slug")
    @classmethod
    def validate_optional_name_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content is required")
        return value


class ReportRead(CamelModel):
    id: int
    name: str
    slug: str
    source: ReportSource
    content: str
    metadata: ReportReadMetadata = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_metadata(cls, value: object) -> object:
        if value is None:
            return {}
        return value

    @field_serializer("metadata", when_used="json")
    def serialize_metadata(self, value: ReportReadMetadata) -> dict[str, object]:
        payload = cast(dict[str, object], value.model_dump(by_alias=True))
        analysis = value.analysis
        if analysis is None:
            _ = payload.pop("analysis", None)
        else:
            payload["analysis"] = analysis.model_dump(by_alias=True, exclude_none=True)
        created_by = value.created_by
        if created_by is None:
            _ = payload.pop("createdBy", None)
        else:
            payload["createdBy"] = created_by.model_dump(by_alias=True, exclude_none=True)
        return payload


class ReportUpdate(CamelModel):
    content: str | None = Field(default=None, min_length=1)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("Content is required")
        return value

    @model_validator(mode="after")
    def validate_payload(self) -> ReportUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "content" in self.model_fields_set and self.content is None:
            raise ValueError("Content is required")
        return self

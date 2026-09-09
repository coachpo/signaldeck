"""Closed, frozen presentation declarations; references use the mapping namespace."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import Field, model_validator

from app.domain.mapping_types import reference_schema
from app.domain.schema_contract import reject
from app.domain.tool_contracts import QUALIFIED_ID
from app.schemas.common import CamelModel

if TYPE_CHECKING:
    from app.domain.definitions import PackageDefinition, WorkflowDefinition


class Declaration(CamelModel):
    @model_validator(mode="before")
    @classmethod
    def reject_null_fields(cls, value: Any) -> Any:
        if isinstance(value, dict) and any(item is None for item in value.values()):
            raise ValueError("Presentation fields must be omitted rather than null")
        return value


class InputHint(Declaration):
    ref: str = Field(pattern=r"^workflow\.input\.[^.]+(?:\.[^.]+)*$")
    control: Literal["text", "textarea"]
    placeholder: str | None = Field(default=None, max_length=2000, exclude_if=lambda v: v is None)


class InputTitle(Declaration):
    kind: Literal["input"]
    ref: str = Field(pattern=r"^workflow\.input\.[^.]+(?:\.[^.]+)*$")


class StaticTitle(Declaration):
    kind: Literal["static"]
    text: str = Field(min_length=1, max_length=200)


class ValueSection(Declaration):
    kind: Literal["markdown", "value", "receipt", "sources", "dataTime"]
    ref: str = Field(pattern=r"^(workflow\.output|nodes\.[^.]+\.output)(\.[^.]+)*$")
    label: str = Field(min_length=1, max_length=200)
    required: bool = False


class NoticeSection(Declaration):
    kind: Literal["notice"]
    ref: str = Field(pattern=r"^(workflow\.output|nodes\.[^.]+\.output)(\.[^.]+)*$")
    label: str = Field(min_length=1, max_length=200)
    required: bool = False
    severity: Literal["info", "warning", "missing"]


class LinkSection(Declaration):
    kind: Literal["link"]
    ref: str = Field(pattern=r"^nodes\.[^.]+\.output(\.[^.]+)*$")
    label: str = Field(min_length=1, max_length=200)
    required: bool = False
    tool_id: str = Field(pattern=QUALIFIED_ID)
    link_key: str = Field(min_length=1, max_length=120)


class WorkflowPresentation(Declaration):
    version: Literal["signaldeck.presentation/1"]
    input_hints: list[InputHint] = Field(default_factory=list, max_length=1000)
    title: Annotated[InputTitle | StaticTitle, Field(discriminator="kind")] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    sections: list[
        Annotated[ValueSection | NoticeSection | LinkSection, Field(discriminator="kind")]
    ] = Field(default_factory=list, max_length=1000)


def validate_presentation(
    workflow: WorkflowDefinition, package: PackageDefinition, path: str
) -> None:
    presentation = workflow.presentation
    if presentation is None:
        return
    namespace = {
        "workflow.input": workflow.input_schema,
        "workflow.output": workflow.output_schema,
        **{
            f"nodes.{key}.output": package.agents[node.uses].output_schema
            for key, node in workflow.nodes.items()
        },
    }
    seen = set()
    for index, hint in enumerate(presentation.input_hints):
        location = f"{path}.inputHints.{index}.ref"
        schema, _ = reference_schema(hint.ref, namespace, location)
        if schema["type"] != "string":
            reject("presentation_type", location, "Input controls require a string schema")
        if hint.ref in seen:
            reject("duplicate_hint", location, "Input hint references must be unique")
        seen.add(hint.ref)
    if isinstance(presentation.title, InputTitle):
        schema, _ = reference_schema(presentation.title.ref, namespace, path + ".title.ref")
        if schema["type"] != "string":
            reject("presentation_type", path + ".title.ref", "Run title requires a string schema")
    for index, section in enumerate(presentation.sections):
        location = f"{path}.sections.{index}"
        schema, _ = reference_schema(section.ref, namespace, location + ".ref")
        kind = schema["type"]
        valid = True
        if section.kind in {"markdown", "dataTime"}:
            valid = kind == "string"
        elif section.kind == "sources":
            valid = kind == "array"
        elif section.kind == "notice":
            valid = kind == "string" or (kind == "array" and schema["items"]["type"] == "string")
        if not valid:
            reject("presentation_type", location + ".ref", "Section schema has incompatible type")
        if isinstance(section, LinkSection):
            node = workflow.nodes[section.ref.split(".")[1]]
            if section.tool_id not in package.agents[node.uses].tools:
                reject(
                    "presentation_tool_grant", location + ".toolId", "Link requires node tool grant"
                )

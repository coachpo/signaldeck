"""Public annotations stay opt-in and frozen alongside their source contracts."""

import json
from copy import deepcopy
from io import StringIO

import pytest
from ruamel.yaml import YAML

from app.domain.compiler import compile_package
from app.domain.definition_parser import parse_package_source
from app.domain.schema_contract import DomainValidationError, validate_schema, validate_value
from tests.test_dag_compiler import package

MARKER = {"x-signaldeck-schema": "signaldeck.schema/2"}


def test_old_definition_keeps_hash_and_absent_fields_through_roundtrip() -> None:
    compiled = compile_package(package())
    assert (
        compiled.content_hash == "97f5fdbc44285fbabf7a200a2d7f7825ae5af4cb31e9aa822d5b44073dd799b6"
    )
    exported = compiled.model_dump(mode="json", by_alias=True)["package"]
    assert "presentation" not in exported["workflows"]["main"]
    assert "description" not in exported["workflows"]["main"]
    assert compile_package(exported).content_hash == compiled.content_hash


def test_annotations_validate_without_materializing_values() -> None:
    schema = {
        "type": "object",
        **MARKER,
        "properties": {
            "subject": {"type": "string", **MARKER, "default": "", "examples": ["A", ""]},
            "absent": {"type": "null", **MARKER, "default": None, "examples": [None]},
        },
        "default": {"subject": "draft"},
        "examples": [{}, {"absent": None}],
    }
    before = deepcopy(schema)
    value = {}
    validate_schema(schema)
    validate_value(schema, value)
    assert schema == before
    assert value == {}
    schema["required"] = ["subject"]
    schema.pop("examples")
    with pytest.raises(DomainValidationError):
        validate_value(schema, value)


@pytest.mark.parametrize(
    "schema,path",
    [
        ({"type": "string", "default": "x"}, ".default"),
        ({"type": "string", "examples": ["x"]}, ".examples"),
        ({"type": "string", **MARKER, "default": None}, ".default"),
        ({"type": "integer", **MARKER, "examples": ["invalid"]}, ".examples.0"),
        ({"type": "string", "x-signaldeck-schema": "signaldeck.schema/3"}, ".x-signaldeck-schema"),
        ({"type": "string", "x-signaldeck-schema": []}, ".x-signaldeck-schema"),
        (
            {"type": "object", **MARKER, "properties": {"x": {"type": "string", "default": "x"}}},
            ".properties.x.default",
        ),
        ({"type": "object", **MARKER, "default": {"undeclared": 1}}, ".default"),
    ],
)
def test_annotation_versions_and_closed_values(schema: dict, path: str) -> None:
    with pytest.raises(DomainValidationError) as error:
        validate_schema(schema)
    assert error.value.diagnostics[0].path == "$" + path


def presented_package() -> dict:
    value = package()
    value["workflows"]["main"]["description"] = "A saved workflow"
    value["workflows"]["main"]["presentation"] = {
        "version": "signaldeck.presentation/1",
        "title": {"kind": "input", "ref": "workflow.input.text"},
        "inputHints": [
            {"ref": "workflow.input.text", "control": "textarea", "placeholder": "Draft"}
        ],
        "sections": [
            {"kind": "markdown", "ref": "workflow.output.text", "label": "Answer"},
            {"kind": "value", "ref": "nodes.first.output", "label": "Confirmed"},
            {
                "kind": "notice",
                "ref": "nodes.first.output.text",
                "label": "Info",
                "severity": "info",
            },
            {
                "kind": "link",
                "ref": "nodes.first.output.text",
                "label": "Open",
                "toolId": "example/echo/copy",
                "linkKey": "details",
            },
        ],
    }
    return value


def test_presentation_roundtrips_and_changes_hash_with_declarations() -> None:
    value = presented_package()
    compiled = compile_package(value)
    stream = StringIO()
    YAML().dump(compiled.package.model_dump(mode="json", by_alias=True), stream)
    restored = parse_package_source(stream.getvalue())
    assert restored.content_hash == compiled.content_hash
    assert restored.content_hash != compile_package(package()).content_hash
    assert restored.package.workflows["main"].presentation.title.ref == "workflow.input.text"
    value["workflows"]["main"]["presentation"]["sections"][0]["label"] = "Renamed"
    assert compile_package(value).content_hash != compiled.content_hash


@pytest.mark.parametrize("name", ["includeRisk", "reportId", "collection", "unfamiliar"])
def test_business_like_names_are_ordinary_declared_fields(name: str) -> None:
    value = presented_package()
    # Rename the field and every explicit reference; presentation needs no business dictionary.
    value = json.loads(
        json.dumps(value)
        .replace('"text": {"type"', f'"{name}": {{"type"')
        .replace('["text"]', f'["{name}"]')
        .replace('.text"', f'.{name}"')
    )
    compiled = compile_package(value)
    assert compiled.package.workflows["main"].presentation.title.ref == f"workflow.input.{name}"


@pytest.mark.parametrize("field", ["presentation", "description"])
def test_explicit_null_optional_workflow_declarations_are_rejected(field: str) -> None:
    value = package()
    value["workflows"]["main"][field] = None
    with pytest.raises(DomainValidationError):
        compile_package(value)


@pytest.mark.parametrize(
    "section,code",
    [
        ({"kind": "markdown", "ref": "workflow.output", "label": "Bad"}, "presentation_type"),
        ({"kind": "sources", "ref": "workflow.output.text", "label": "Bad"}, "presentation_type"),
        ({"kind": "value", "ref": "nodes.absent.output", "label": "Bad"}, "unknown_reference"),
        ({"kind": "value", "ref": "workflow.output.absent", "label": "Bad"}, "unknown_reference"),
        ({"kind": "value", "ref": "workflow.input.text", "label": "Bad"}, "invalid_definition"),
        (
            {"kind": "notice", "ref": "workflow.output", "label": "Bad", "severity": "missing"},
            "presentation_type",
        ),
        (
            {
                "kind": "link",
                "ref": "nodes.first.output",
                "label": "Bad",
                "toolId": "other/tool/read",
                "linkKey": "x",
            },
            "presentation_tool_grant",
        ),
        (
            {"kind": "value", "ref": "workflow.output", "label": "Bad", "business": "x"},
            "invalid_definition",
        ),
    ],
)
def test_selector_contract_is_closed_and_source_located(section: dict, code: str) -> None:
    value = presented_package()
    value["workflows"]["main"]["presentation"]["sections"] = [section]
    stream = StringIO()
    YAML().dump(json.loads(json.dumps(value)), stream)
    with pytest.raises(DomainValidationError) as error:
        parse_package_source(stream.getvalue())
    diagnostic = error.value.diagnostics[0]
    assert diagnostic.code == code
    assert diagnostic.line is not None
    assert diagnostic.column is not None
    assert ".sections.0." in diagnostic.path
    expected_field = diagnostic.path.rsplit(".", 1)[-1]
    assert expected_field + ":" in stream.getvalue().splitlines()[diagnostic.line - 1]


def test_default_invalid_source_location_is_on_annotation() -> None:
    value = package()
    value["workflows"]["main"]["inputSchema"] = deepcopy(value["workflows"]["main"]["inputSchema"])
    value["workflows"]["main"]["inputSchema"]["properties"]["text"].update(
        {**MARKER, "default": 12}
    )
    stream = StringIO()
    YAML().dump(json.loads(json.dumps(value)), stream)
    with pytest.raises(DomainValidationError) as error:
        parse_package_source(stream.getvalue())
    diagnostic = error.value.diagnostics[0]
    assert diagnostic.path == "$.workflows.main.inputSchema.properties.text.default"
    assert "default: 12" in stream.getvalue().splitlines()[diagnostic.line - 1]


@pytest.mark.parametrize("target", ["title", "section", "strategy"])
def test_extra_field_named_like_union_tag_retains_exact_source_path(target: str) -> None:
    value = presented_package()
    if target == "title":
        declaration = value["workflows"]["main"]["presentation"]["title"]
        expected = "$.workflows.main.presentation.title.input"
    elif target == "section":
        declaration = value["workflows"]["main"]["presentation"]["sections"][0]
        expected = "$.workflows.main.presentation.sections.0.markdown"
    else:
        declaration = value["agents"]["echo"]["strategy"]
        expected = "$.agents.echo.strategy." + declaration["kind"]
    declaration[declaration["kind"]] = "unsupported field"
    output = StringIO()
    yaml = YAML()
    yaml.representer.ignore_aliases = lambda *_: True
    yaml.dump(value, output)
    with pytest.raises(DomainValidationError) as error:
        parse_package_source(output.getvalue())
    diagnostic = error.value.diagnostics[0]
    assert diagnostic.path == expected
    assert diagnostic.line is not None
    assert "unsupported field" in output.getvalue().splitlines()[diagnostic.line - 1]

from __future__ import annotations

from copy import deepcopy

import pytest

from app.domain.compiler import compile_package, validate_agent_tool_contract
from app.domain.definition_parser import parse_package_source
from app.domain.mappings import evaluate_condition, resolve_mapping
from app.domain.schema_contract import (
    DomainValidationError,
    materialize_schema,
    validate_schema,
    validate_value,
)


def package() -> dict:
    text = {"type": "string"}
    record = {"type": "object", "properties": {"text": text}, "required": ["text"]}
    return {
        "apiVersion": "signaldeck.workflowPackage/v2",
        "metadata": {"key": "demo", "name": "Demo"},
        "agents": {
            "echo": {
                "inputSchema": record,
                "outputSchema": record,
                "strategy": {"kind": "deterministic", "toolId": "example/echo/copy"},
                "tools": ["example/echo/copy"],
            }
        },
        "workflows": {
            "main": {
                "inputSchema": record,
                "outputSchema": record,
                "nodes": {
                    "first": {"uses": "echo", "inputMapping": {"ref": "workflow.input"}},
                    "second": {"uses": "echo", "inputMapping": {"ref": "nodes.first.output"}},
                },
                "outputMapping": {"ref": "nodes.second.output"},
            }
        },
    }


def test_compiler_merges_all_edge_sources_and_is_order_independent() -> None:
    value = package()
    nodes = value["workflows"]["main"]["nodes"]
    nodes["second"]["dependsOn"] = ["first"]
    nodes["second"]["condition"] = {
        "op": "ne",
        "args": [{"ref": "nodes.first.output.text"}, {"value": ""}],
    }
    first = compile_package(value)
    edge = first.plans["main"].edges[0]
    assert edge.sources == ["condition", "control", "input"]
    assert len(edge.paths) == 3
    assert first.plans["main"].node_order == ["first", "second"]
    value["workflows"]["main"]["nodes"] = dict(reversed(list(nodes.items())))
    assert compile_package(value).content_hash == first.content_hash


@pytest.mark.parametrize("source", ["input", "condition"])
def test_cycles_through_inferred_edges_are_located(source: str) -> None:
    value = package()
    node = value["workflows"]["main"]["nodes"]["first"]
    if source == "input":
        node["inputMapping"] = {"ref": "nodes.second.output"}
    else:
        node["condition"] = {"op": "exists", "args": [{"ref": "nodes.second.output"}]}
    with pytest.raises(DomainValidationError) as error:
        compile_package(value)
    assert error.value.diagnostics[0].code == "dependency_cycle"
    assert any("first" in diagnostic.path for diagnostic in error.value.diagnostics)


@pytest.mark.parametrize(
    "reference", ["nodes.missing.output", "nodes.first.output.missing", "agent.input"]
)
def test_unknown_reference_and_wrong_scope_rejected(reference: str) -> None:
    value = package()
    value["workflows"]["main"]["nodes"]["second"]["inputMapping"] = {"ref": reference}
    with pytest.raises(DomainValidationError) as error:
        compile_package(value)
    assert error.value.diagnostics[0].code == "unknown_reference"


def test_type_mismatch_rejected_before_launch() -> None:
    value = package()
    value["workflows"]["main"]["inputSchema"] = {"type": "string"}
    with pytest.raises(DomainValidationError, match="incompatible"):
        compile_package(value)


def test_agent_reuse_and_recursive_strategy_rejection() -> None:
    value = package()
    value["workflows"]["other"] = deepcopy(value["workflows"]["main"])
    compiled = compile_package(value)
    assert len(compiled.package.agents) == 1
    assert len(compiled.plans) == 2
    value["agents"]["echo"]["strategy"] = {"kind": "agent", "uses": "echo"}
    with pytest.raises(DomainValidationError):
        compile_package(value)


def test_explicit_missing_preserves_absence_without_fabricating_node_output() -> None:
    namespace = {"nodes": {"a": {}}, "workflow": {"input": {}}}
    mapping = {
        "object": {"items": {"array": [{"ref": "nodes.a.output", "onMissing": {"value": None}}]}}
    }
    assert resolve_mapping(mapping, namespace) == {"items": [None]}
    assert namespace["nodes"]["a"] == {}
    with pytest.raises(DomainValidationError, match="unavailable"):
        resolve_mapping({"ref": "nodes.a.output"}, namespace)
    assert not evaluate_condition({"op": "exists", "args": [{"ref": "nodes.a.output"}]}, namespace)


def test_optional_reference_requires_explicit_handling() -> None:
    value = package()
    value["workflows"]["main"]["inputSchema"] = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
    }
    value["workflows"]["main"]["nodes"]["first"]["inputMapping"] = {
        "object": {"text": {"ref": "workflow.input.text"}}
    }
    with pytest.raises(DomainValidationError, match="onMissing"):
        compile_package(value)
    value["workflows"]["main"]["nodes"]["first"]["inputMapping"]["object"]["text"]["onMissing"] = {
        "value": "fallback"
    }
    compile_package(value)


def test_deterministic_contract_checks_transformation() -> None:
    agent = compile_package(package()).package.agents["echo"]
    validate_agent_tool_contract(agent, agent.input_schema, agent.output_schema)
    with pytest.raises(DomainValidationError):
        validate_agent_tool_contract(agent, {"type": "integer"}, agent.output_schema)


@pytest.mark.parametrize(
    "keyword",
    [
        "additionalProperties",
        "patternProperties",
        "allowAdditionalProperties",
        "format",
        "$ref",
        "anyOf",
    ],
)
def test_unsupported_schema_constraints_are_never_ignored(keyword: str) -> None:
    with pytest.raises(DomainValidationError):
        validate_schema({"type": "object", keyword: False})


def test_closed_schema_and_safe_diagnostics() -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string", "minLength": 4}},
        "required": ["name"],
    }
    assert materialize_schema(schema)["unevaluatedProperties"] is False
    with pytest.raises(DomainValidationError) as error:
        validate_value(schema, {"name": "x", "apiKey": "TEST-CREDENTIAL"})
    assert "TEST-CREDENTIAL" not in str(error.value)
    assert "apiKey" not in str(error.value)


@pytest.mark.parametrize(
    "source", ["a: &anchor {}\nb: *anchor", "a: 1\na: 2", "a: !!str x", "a: .nan", "a: 2026-01-01"]
)
def test_yaml_unsafe_sources_rejected(source: str) -> None:
    with pytest.raises(DomainValidationError):
        parse_package_source(source)


def test_yaml_compiler_errors_have_source_locations() -> None:
    from io import StringIO

    from ruamel.yaml import YAML

    value = package()
    value["workflows"]["main"]["nodes"]["second"]["dependsOn"] = ["unknown"]
    # Round-trip serialization creates anchors for shared fixture dictionaries; remove sharing.
    import json

    stream = StringIO()
    YAML().dump(json.loads(json.dumps(value)), stream)
    with pytest.raises(DomainValidationError) as error:
        parse_package_source(stream.getvalue())
    assert error.value.diagnostics[0].line is not None


def test_missing_branch_join_requires_fallback() -> None:
    value = package()
    node = value["workflows"]["main"]["nodes"]["second"]
    node["acceptUpstreamStates"] = ["succeeded", "skipped", "failed"]
    with pytest.raises(DomainValidationError, match="onMissing"):
        compile_package(value)
    node["inputMapping"]["onMissing"] = {"value": {"text": "No result"}}
    compile_package(value)


def test_composed_constant_cannot_bypass_enum_constraint() -> None:
    value = package()
    value["agents"]["echo"]["inputSchema"] = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "enum": [{"text": "allowed"}],
    }
    value["workflows"]["main"]["nodes"]["first"]["inputMapping"] = {
        "object": {"text": {"value": "rejected"}}
    }
    with pytest.raises(DomainValidationError, match="enum"):
        compile_package(value)


def test_schema_keyword_diagnostic_keeps_nested_location() -> None:
    value = package()
    value["agents"]["echo"]["outputSchema"] = {
        "type": "object",
        "properties": {"text": {"type": "string", "format": "uri"}},
    }
    with pytest.raises(DomainValidationError) as error:
        compile_package(value)
    diagnostic = error.value.diagnostics[0]
    assert diagnostic.code == "unsupported_schema"
    assert diagnostic.path == "$.agents.echo.outputSchema.properties.text.format"


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [(1, 1.0, True), (True, 1, False), ([True], [1], False), ({"a": 1}, {"a": 1.0}, True)],
)
def test_condition_equality_has_json_scalar_semantics(left, right, expected) -> None:
    assert (
        evaluate_condition({"op": "eq", "args": [{"value": left}, {"value": right}]}, {})
        is expected
    )


def test_nonfinite_mapping_constant_rejected() -> None:
    value = package()
    value["workflows"]["main"]["nodes"]["first"]["inputMapping"] = {"value": float("nan")}
    with pytest.raises(DomainValidationError):
        compile_package(value)


def test_artifact_envelope_field_is_reserved_at_every_schema_depth() -> None:
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object", "properties": {"$artifact": {"type": "string"}}},
            }
        },
    }
    with pytest.raises(DomainValidationError) as error:
        validate_schema(schema)
    assert error.value.diagnostics[0].code == "reserved_schema_field"
    assert error.value.diagnostics[0].path == "$.properties.items.items.properties.$artifact"
    business = {
        "type": "object",
        "properties": {
            "digest": {"type": "string"},
            "size": {"type": "integer"},
            "text": {"type": "string"},
        },
        "required": ["digest", "size", "text"],
    }
    validate_value(
        business, {"digest": "ordinary-hash", "size": 12, "text": "$artifact is reserved"}
    )
    with pytest.raises(DomainValidationError):
        validate_value(
            business,
            {"digest": "hash", "size": 12, "text": "note", "$artifact": {"digest": "hash"}},
        )


def test_cache_policy_requires_selected_tool_and_changes_revision_identity() -> None:
    definition = package()
    uncached = compile_package(definition)
    assert uncached.package.agents["echo"].tool_cache == {}
    definition["agents"]["echo"]["toolCache"] = {"example/other/read": {"ttlSeconds": 60}}
    with pytest.raises(DomainValidationError) as error:
        compile_package(definition)
    assert error.value.diagnostics[0].path == "$.agents.echo"
    definition["agents"]["echo"]["toolCache"] = {"example/echo/copy": {"ttlSeconds": 60}}
    cached = compile_package(definition)
    policy = cached.package.agents["echo"].tool_cache["example/echo/copy"]
    assert policy.scope == "resource"
    assert policy.key == "release_input_resources"
    assert policy.ttl_seconds == 60
    assert cached.content_hash != uncached.content_hash
    definition["agents"]["echo"]["toolCache"]["example/echo/copy"].update(
        {"scope": "resource", "key": "release_input_resources"}
    )
    assert compile_package(definition).content_hash == cached.content_hash

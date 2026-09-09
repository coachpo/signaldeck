"""Deterministic compilation of the merged Workflow dependency graph."""

from __future__ import annotations

import hashlib
import heapq
import json
from typing import Any

from pydantic import ValidationError

from app.domain.definitions import (
    AgentDefinition,
    CompiledPackage,
    DependencyEdge,
    DeterministicStrategy,
    PackageDefinition,
    WorkflowDefinition,
    WorkflowPlan,
)
from app.domain.mapping_types import check_mapping, check_mapping_availability, reference_schema
from app.domain.mappings import condition_references, mapping_references
from app.domain.presentation import validate_presentation
from app.domain.schema_contract import Diagnostic, DomainValidationError, reject


def compile_package(package: PackageDefinition | dict[str, Any]) -> CompiledPackage:
    if not isinstance(package, PackageDefinition):
        try:
            package = PackageDefinition.model_validate(package)
        except ValidationError as error:
            diagnostics: list[Diagnostic] = []
            for item in error.errors(include_input=False):
                prefix = _definition_error_path(package, item["loc"])
                cause = item.get("ctx", {}).get("error")
                if isinstance(cause, DomainValidationError):
                    diagnostics.extend(
                        Diagnostic(child.code, prefix + child.path.removeprefix("$"), child.message)
                        for child in cause.diagnostics
                    )
                else:
                    diagnostics.append(
                        Diagnostic(
                            "invalid_definition",
                            prefix,
                            "Invalid definition field: " + item["type"],
                        )
                    )
            raise DomainValidationError(diagnostics) from None
    for key, agent in package.agents.items():
        _check_agent_references(agent, f"$.agents.{key}")
    plans = {
        key: _compile_workflow(key, workflow, package)
        for key, workflow in sorted(package.workflows.items())
    }
    canonical = package.model_dump(mode="json", by_alias=True)
    for workflow in canonical["workflows"].values():
        for node in workflow["nodes"].values():
            node["dependsOn"] = sorted(set(node["dependsOn"]))
            node["acceptUpstreamStates"] = sorted(node["acceptUpstreamStates"])
    for agent in canonical["agents"].values():
        agent["tools"] = sorted(set(agent["tools"]))
        agent["resources"] = sorted(set(agent["resources"]))
    content_hash = hashlib.sha256(
        json.dumps(
            canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()
    return CompiledPackage(
        package=PackageDefinition.model_validate(canonical), plans=plans, content_hash=content_hash
    )


def _definition_error_path(value: Any, location: tuple[str | int, ...]) -> str:
    """Discriminated union tags are model metadata, not YAML path components."""
    path = "$"
    for index, part in enumerate(location):
        if isinstance(value, dict):
            repeated_tag = index + 1 < len(location) and location[index + 1] == part
            if value.get("kind") == part and (part not in value or repeated_tag):
                continue
            value = value.get(part)
        elif isinstance(value, list) and isinstance(part, int) and part < len(value):
            value = value[part]
        else:
            value = None
        path += f".{part}"
    return path


def _check_agent_references(agent: AgentDefinition, path: str) -> None:
    if not isinstance(agent.strategy, DeterministicStrategy):
        return
    for reference, location in mapping_references(
        agent.strategy.input_mapping, path + ".strategy.inputMapping"
    ):
        if not reference.startswith("agent.input"):
            reject(
                "invalid_reference_scope",
                location,
                "Agent tool input can only reference its own input",
            )
        reference_schema(reference, {"agent.input": agent.input_schema}, location)
    for reference, location in mapping_references(
        agent.strategy.output_mapping, path + ".strategy.outputMapping"
    ):
        if not (
            reference == "agent.input"
            or reference.startswith("agent.input.")
            or reference == "tool.output"
            or reference.startswith("tool.output.")
        ):
            reject(
                "invalid_reference_scope",
                location,
                "Agent output can only reference its input or tool result",
            )


def validate_agent_tool_contract(
    agent: AgentDefinition, tool_input: dict[str, Any], tool_output: dict[str, Any], path: str = "$"
) -> None:
    """Resolve deterministic strategy types against the selected immutable tool contract."""
    if isinstance(agent.strategy, DeterministicStrategy):
        namespace = {"agent.input": agent.input_schema, "tool.output": tool_output}
        check_mapping(agent.strategy.input_mapping, tool_input, namespace, path + ".inputMapping")
        check_mapping(
            agent.strategy.output_mapping, agent.output_schema, namespace, path + ".outputMapping"
        )


def _compile_workflow(
    key: str, workflow: WorkflowDefinition, package: PackageDefinition
) -> WorkflowPlan:
    root = f"$.workflows.{key}"
    namespace = {"workflow.input": workflow.input_schema}
    for node_key, node in workflow.nodes.items():
        if node.uses not in package.agents:
            reject(
                "unknown_agent", f"{root}.nodes.{node_key}.uses", "Referenced Agent is not defined"
            )
        namespace[f"nodes.{node_key}.output"] = package.agents[node.uses].output_schema
    validate_presentation(workflow, package, root + ".presentation")
    edge_sources: dict[tuple[str, str], set[str]] = {}
    edge_paths: dict[tuple[str, str], set[str]] = {}
    dependencies: dict[str, set[str]] = {node_key: set() for node_key in workflow.nodes}
    for node_key, node in sorted(workflow.nodes.items()):
        path = f"{root}.nodes.{node_key}"
        references = [
            (dep, "control", f"{path}.dependsOn.{index}")
            for index, dep in enumerate(node.depends_on)
        ]
        for origin, refs in (
            ("input", mapping_references(node.input_mapping, path + ".inputMapping")),
            (
                "condition",
                condition_references(node.condition, path + ".condition") if node.condition else [],
            ),
        ):
            for reference, location in refs:
                reference_schema(reference, namespace, location)
                if reference.startswith("nodes."):
                    references.append((reference.split(".")[1], origin, location))
        for source, origin, location in references:
            if source not in workflow.nodes:
                reject("unknown_node", location, "Dependency node is not defined")
            dependencies[node_key].add(source)
            edge_sources.setdefault((source, node_key), set()).add(origin)
            edge_paths.setdefault((source, node_key), set()).add(location)
        check_mapping(
            node.input_mapping,
            package.agents[node.uses].input_schema,
            namespace,
            path + ".inputMapping",
        )
        if set(node.accept_upstream_states) - {"succeeded"}:
            check_mapping_availability(
                node.input_mapping, namespace, path + ".inputMapping", set(dependencies[node_key])
            )
        if node.condition:
            _check_condition_types(node.condition, namespace, path + ".condition")
    check_mapping(
        workflow.output_mapping, workflow.output_schema, namespace, root + ".outputMapping"
    )
    order = _topological_order(dependencies, edge_paths)
    edges = [
        DependencyEdge.model_validate(
            {
                "source": source,
                "target": target,
                "sources": sorted(origins),
                "paths": sorted(edge_paths[(source, target)]),
            }
        )
        for (source, target), origins in sorted(edge_sources.items())
    ]
    return WorkflowPlan(
        workflow_key=key,
        node_order=order,
        dependencies={name: sorted(deps) for name, deps in sorted(dependencies.items())},
        edges=edges,
    )


def _topological_order(
    dependencies: dict[str, set[str]], paths: dict[tuple[str, str], set[str]]
) -> list[str]:
    remaining = {name: set(deps) for name, deps in dependencies.items()}
    ready = [name for name, deps in remaining.items() if not deps]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        current = heapq.heappop(ready)
        order.append(current)
        for target in sorted(remaining):
            if current in remaining[target]:
                remaining[target].remove(current)
                if not remaining[target]:
                    heapq.heappush(ready, target)
    if len(order) != len(dependencies):
        blocked = set(dependencies) - set(order)
        diagnostics = [
            Diagnostic(
                "dependency_cycle", location, "Dependency is part of a cycle or blocked by a cycle"
            )
            for (source, target), locations in sorted(paths.items())
            if source in blocked and target in blocked
            for location in sorted(locations)
        ]
        raise DomainValidationError(diagnostics)
    return order


def _check_condition_types(condition: dict[str, Any], namespace: dict[str, Any], path: str) -> None:
    op, args = condition["op"], condition["args"]
    if op in {"all", "any", "not"}:
        for index, child in enumerate(args):
            _check_condition_types(child, namespace, f"{path}.args.{index}")
        return
    if op == "exists":
        return
    kinds = []
    for index, arg in enumerate(args):
        check_mapping_availability(arg, namespace, f"{path}.args.{index}")
        if "ref" in arg:
            schema, optional = reference_schema(arg["ref"], namespace, f"{path}.args.{index}")
            if optional and "onMissing" not in arg:
                reject(
                    "missing_mapping",
                    path,
                    "Optional condition reference requires onMissing or exists",
                )
            if "onMissing" in arg:
                check_mapping(arg["onMissing"], schema, namespace, path)
            kinds.append(schema["type"])
        elif "value" in arg:
            value = arg["value"]
            kinds.append(
                "null"
                if value is None
                else {
                    str: "string",
                    int: "integer",
                    float: "number",
                    bool: "boolean",
                    list: "array",
                    dict: "object",
                }.get(type(value))
            )
        else:
            kinds.append("object" if "object" in arg else "array")
    compatible = kinds[0] == kinds[1] or set(kinds) == {"integer", "number"}
    if not compatible or (
        op not in {"eq", "ne"} and kinds[0] not in {"string", "integer", "number"}
    ):
        reject("condition_type", path, "Condition operands have incompatible types")

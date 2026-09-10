"""Classify unresolved evidence solely from the Run's explicit frozen tool effects."""

from collections.abc import Iterable, Mapping
from typing import Any


def _readonly_execution(
    spec: Mapping[str, Any], item: Mapping[str, Any], effects: dict[str, list[Any]]
) -> bool:
    """Use explicit frozen execution contracts, never defaults for missing history."""
    definition = spec.get("definition")
    if not isinstance(definition, dict):
        return False
    try:
        node = definition["workflows"][spec["workflowKey"]]["nodes"][item["nodeId"]]
        agent = definition["agents"][node["uses"]]
        strategy = agent["strategy"]
        if not isinstance(strategy, dict):
            return False
        if item.get("kind") == "model":
            # A model response only proposes calls. Any tool execution has its own
            # logical evidence; granting write tools does not turn model I/O into a write.
            return strategy.get("kind") == "model"
        grants = agent["tools"]
        if not isinstance(grants, list) or not all(
            isinstance(tool_id, str) and effects.get(tool_id) == ["read"] for tool_id in grants
        ):
            return False
        return strategy.get("kind") == "model" or (
            strategy.get("kind") == "deterministic" and strategy.get("toolId") in grants
        )
    except (KeyError, TypeError):
        return False


def unknown_evidence(
    spec: Mapping[str, Any], evidence: Iterable[Mapping[str, Any]]
) -> tuple[list[str], list[str]]:
    """Return potential write effects and known read result uncertainties.

    Missing/ambiguous historical contracts remain conservative. Do not apply the
    ToolDefinition default to historical data or infer effects from names/errors.
    Network attempts are not logical effects after operation reconciliation.
    """
    effects: dict[str, list[Any]] = {}
    for release in spec.get("pluginReleases", []):
        for tool in release.get("tools", []):
            effects.setdefault(tool.get("toolId"), []).append(tool.get("effect"))
    writes: list[str] = []
    reads: list[str] = []
    for item in evidence:
        if item.get("status") != "unknown" or item.get("kind") == "attempt":
            continue
        tool_id = item.get("toolId")
        kind = item.get("kind")
        readonly = (
            isinstance(tool_id, str) and effects.get(tool_id) == ["read"]
            if kind == "tool"
            else kind in {"model", "agent", "node"} and _readonly_execution(spec, item, effects)
        )
        target = reads if readonly else writes
        target.append(item["id"])
    return writes, reads

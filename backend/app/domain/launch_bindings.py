"""Deterministic identity of reviewed launch bindings."""

from typing import Any

from pydantic import JsonValue

from app.domain.budgets import effective_execution_options
from app.domain.execution import ResolvedRunSpec


def binding_value(
    package_hash: str,
    workflow_key: str,
    parameters: JsonValue,
    models: dict[str, Any],
    resources: dict[str, Any],
    releases: list[dict[str, Any]],
    execution_options: dict[str, Any] | None = None,
    effective_agent_budgets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "executionOptions": execution_options or {"agentBudgets": {}},
        "effectiveAgentBudgets": effective_agent_budgets or {},
        "packageHash": package_hash,
        "workflowKey": workflow_key,
        "parameters": parameters,
        "models": models,
        "resources": resources,
        "plugins": sorted(releases, key=lambda item: item["pluginId"]),
    }


def spec_bindings(spec: ResolvedRunSpec) -> dict[str, Any]:
    return binding_value(
        spec.package_hash,
        spec.workflow_key,
        spec.parameters,
        spec.model_bindings,
        spec.resource_bindings,
        spec.plugin_releases,
        spec.execution_options.model_dump(mode="json", by_alias=True),
        {
            key: budget.model_dump(mode="json", by_alias=True)
            for key, budget in effective_execution_options(spec).agent_budgets.items()
        },
    )

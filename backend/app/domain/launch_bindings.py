"""Deterministic identity of reviewed launch bindings."""

from typing import Any

from pydantic import JsonValue

from app.domain.execution import ResolvedRunSpec


def binding_value(
    package_hash: str,
    workflow_key: str,
    parameters: JsonValue,
    models: dict[str, Any],
    resources: dict[str, Any],
    releases: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
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
    )

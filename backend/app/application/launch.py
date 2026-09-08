"""Resolve a Workflow Package into an atomic, immutable launch command."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from pydantic import JsonValue

from app.domain.compiler import compile_package, validate_agent_tool_contract
from app.domain.definitions import CompiledPackage, DeterministicStrategy, ModelStrategy
from app.domain.execution import (
    ApplicationError,
    LaunchOrigin,
    ResolvedRunSpec,
    RunDetail,
    RunSummary,
)
from app.domain.resources import ResolvedModelConfiguration, ResolvedToolResourceConfiguration
from app.domain.schema_contract import validate_value
from app.domain.tool_contracts import PluginRelease, ToolCatalog


class LaunchStore(Protocol):
    def get_run_by_launch_id(self, launch_id: str) -> RunDetail | None: ...

    def get_package(
        self, package_key: str, revision_hash: str | None = None
    ) -> dict[str, Any] | None: ...

    def get_resource(self, resource_id: str) -> dict[str, Any] | None: ...

    def list_plugins(self) -> list[dict[str, Any]]: ...

    def create_run(self, spec: ResolvedRunSpec, launch_id: str) -> RunSummary: ...


class CoreArtifacts(Protocol):
    def current_digest(self) -> str: ...


class LaunchService:
    def __init__(self, store: LaunchStore, artifacts: CoreArtifacts) -> None:
        self.store = store
        self.artifacts = artifacts

    def launch(
        self,
        package_key: str,
        workflow_key: str,
        parameters: JsonValue,
        *,
        launch_id: str | None = None,
        origin: LaunchOrigin | None = None,
        revision_hash: str | None = None,
    ) -> RunSummary:
        if launch_id is not None:
            previous = self.store.get_run_by_launch_id(launch_id)
            if previous is not None:
                # Retry the original command before touching mutable resource/catalog state.
                # The store still checks the caller's intent and rejects identity conflicts.
                requested = previous.spec.model_copy(
                    update={
                        "package_key": package_key,
                        "workflow_key": workflow_key,
                        "parameters": parameters,
                        "origin": origin or LaunchOrigin(),
                    }
                )
                return self.store.create_run(requested, launch_id)
        revision = self.store.get_package(package_key, revision_hash)
        if revision is None:
            raise ApplicationError(
                "package_not_found", "Workflow Package is unavailable", status=404
            )
        compiled = compile_package(revision["definition"])
        if compiled.content_hash != revision["packageHash"]:
            raise ApplicationError(
                "revision_corrupt", "Stored package revision failed verification"
            )
        if workflow_key not in compiled.package.workflows:
            raise ApplicationError("workflow_not_found", "Workflow is unavailable", status=404)
        workflow = compiled.package.workflows[workflow_key]
        validate_value(workflow.input_schema, parameters, "$.parameters")
        models, resources, releases = self._resolve(compiled, workflow_key)
        catalog = ToolCatalog(tuple(releases))
        grants = tuple(sorted({tool.tool_id for release in releases for tool in release.tools}))
        aliases = {
            item["name"]: catalog.resolve_alias(item["name"])
            for item in catalog.model_tools(grants)
        }
        spec = ResolvedRunSpec(
            run_id=str(uuid4()),
            package_key=package_key,
            workflow_key=workflow_key,
            package_hash=compiled.content_hash,
            definition=compiled.package.model_dump(mode="json", by_alias=True),
            plan=compiled.plans[workflow_key].model_dump(mode="json", by_alias=True),
            parameters=parameters,
            model_bindings=models,
            resource_bindings=resources,
            plugin_releases=[
                release.model_dump(mode="json", by_alias=True) for release in releases
            ],
            tool_aliases=aliases,
            core_artifact=self.artifacts.current_digest(),
            deadline=datetime.now(UTC) + timedelta(seconds=workflow.deadline_seconds),
            origin=origin or LaunchOrigin(),
        )
        return self.store.create_run(spec, launch_id or str(uuid4()))

    def _resource(self, resource_id: str, kind: str) -> dict[str, Any]:
        record = self.store.get_resource(resource_id)
        if record is None or record["kind"] != kind:
            raise ApplicationError("resource_unavailable", "A required resource is unavailable")
        return record

    def _resolve(
        self, compiled: CompiledPackage, workflow_key: str
    ) -> tuple[dict[str, Any], dict[str, Any], list[PluginRelease]]:
        workflow = compiled.package.workflows[workflow_key]
        agents = {
            key: compiled.package.agents[key] for key in {n.uses for n in workflow.nodes.values()}
        }
        required_tools = {tool_id for agent in agents.values() for tool_id in agent.tools}
        required_plugins = {tool_id.rsplit("/", 1)[0] for tool_id in required_tools}
        # Unused descriptors are never parsed or contacted; a broken disabled plugin
        # cannot take ownership of a general read or an unrelated launch.
        releases = [
            PluginRelease.model_validate(item["release"])
            for item in self.store.list_plugins()
            if item["enabled"] and item["pluginId"] in required_plugins
        ]
        catalog = ToolCatalog(tuple(releases))
        models: dict[str, Any] = {}
        resources: dict[str, Any] = {}
        for agent in agents.values():
            if isinstance(agent.strategy, ModelStrategy):
                key = agent.strategy.model_ref
                record = self._resource(key, "model")
                model = ResolvedModelConfiguration.model_validate(
                    {**record["config"], "credentialRevision": record["credentialRevision"]}
                )
                models[key] = model.model_dump(mode="json", by_alias=True)
            for resource_id in agent.resources:
                record = self._resource(resource_id, "tool")
                resource = ResolvedToolResourceConfiguration.model_validate(
                    {**record["config"], "credentialRevision": record["credentialRevision"]}
                )
                resources[resource_id] = resource.model_dump(mode="json", by_alias=True)
            for tool_id in agent.tools:
                try:
                    release, tool = catalog.binding(tool_id)
                except ValueError as exc:
                    raise ApplicationError(
                        "tool_unavailable", "A required tool is unavailable"
                    ) from exc
                if tool_id in agent.tool_cache and tool.effect != "read":
                    raise ApplicationError(
                        "write_cache_forbidden", "Write operations cannot use result caching"
                    )
                if set(tool.resource_requirements) - set(agent.resources):
                    raise ApplicationError(
                        "resource_not_granted", "Tool requires an Agent resource grant"
                    )
                for resource_id in tool.resource_requirements:
                    binding = resources[resource_id]
                    if binding["pluginId"] != release.plugin_id:
                        raise ApplicationError(
                            "resource_owner_mismatch", "Resource belongs to another plugin"
                        )
                    validate_value(release.config_schema, binding["scope"], "$.resource.scope")
                if (
                    isinstance(agent.strategy, DeterministicStrategy)
                    and agent.strategy.tool_id == tool_id
                ):
                    validate_agent_tool_contract(agent, tool.input_schema, tool.output_schema)
        return models, resources, releases

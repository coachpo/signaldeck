"""Non-mutating launch preparation using the canonical admission resolver."""

from typing import Literal

from pydantic import JsonValue, ValidationError

from app.application.launch import LaunchService
from app.domain.compiler import compile_package
from app.domain.definitions import ModelStrategy
from app.domain.execution import ApplicationError
from app.domain.launch_bindings import binding_value, spec_bindings
from app.domain.schema_contract import validate_value
from app.domain.tool_contracts import canonical_digest
from app.schemas.task_experience import PreparationRead, PreparationRequirement


def prepare_task(
    service: LaunchService,
    package_key: str,
    workflow_key: str,
    parameters: JsonValue,
    revision_hash: str | None = None,
    source_run_id: str | None = None,
) -> PreparationRead:
    revision = service.store.get_package(package_key, revision_hash)
    if revision is None:
        raise ApplicationError("package_not_found", "Workflow Package is unavailable", status=404)
    compiled = compile_package(revision["definition"])
    if compiled.content_hash != revision["packageHash"]:
        raise ApplicationError("revision_corrupt", "Stored package revision failed verification")
    workflow = compiled.package.workflows.get(workflow_key)
    if workflow is None:
        raise ApplicationError("workflow_not_found", "Workflow is unavailable", status=404)
    validate_value(workflow.input_schema, parameters, "$.parameters")
    agents = {node.uses: compiled.package.agents[node.uses] for node in workflow.nodes.values()}
    required: dict[str, Literal["model", "tool"]] = {}
    plugins: set[str] = set()
    for agent in agents.values():
        if isinstance(agent.strategy, ModelStrategy):
            required[agent.strategy.model_ref] = "model"
        required.update({key: "tool" for key in agent.resources})
        plugins.update(tool.rsplit("/", 1)[0] for tool in agent.tools)
    requirements = []
    resource_records = {key: service.store.get_resource(key) for key in required}
    for key, kind in sorted(required.items()):
        record = resource_records[key]
        valid = record is not None and record["kind"] == kind
        requirements.append(
            PreparationRequirement(
                id=key,
                kind=kind,
                name=(record or {}).get("config", {}).get("name") or key,
                configured=valid,
                has_credentials=bool((record or {}).get("hasCredentials")),
                config=(record or {}).get("config", {}),
                issue=None if valid else "resource_unavailable",
                model_observation=(
                    (record or {}).get("modelObservation") if kind == "model" else None
                ),
            )
        )
    for requirement in requirements:
        if requirement.model_observation is not None:
            requirement.observation = requirement.model_observation.status
            requirement.observed_at = requirement.model_observation.observed_at
            requirement.observation_error = requirement.model_observation.error_code
    installed = {item["pluginId"]: item for item in service.store.list_plugins()}
    for key in sorted(plugins):
        item = installed.get(key)
        configured = item is not None and bool(item["enabled"])
        requirements.append(
            PreparationRequirement(
                id=key,
                kind="plugin",
                name=key,
                configured=configured,
                issue=None if configured else "plugin_unavailable",
            )
        )
    response = PreparationRead(
        package_key=package_key,
        workflow_key=workflow_key,
        package_hash=compiled.content_hash,
        ready=False,
        requirements=requirements,
        issues=[item.issue for item in requirements if item.issue],
        effective_settings={
            "deadlineSeconds": workflow.deadline_seconds,
            "maxParallelNodes": workflow.max_parallel_nodes,
            "failurePolicy": workflow.failure_policy,
            "agents": {
                key: {
                    "name": agent.name,
                    "strategy": agent.strategy.model_dump(
                        mode="json", by_alias=True, exclude={"prompt"}
                    ),
                    "tools": list(agent.tools),
                    "resources": list(agent.resources),
                    "budget": agent.budget.model_dump(mode="json", by_alias=True),
                }
                for key, agent in agents.items()
            },
        },
    )
    try:
        # The displayed review and its token must describe the same captured values.
        models, resources, releases = service._resolve(
            compiled,
            workflow_key,
            resource_records=resource_records,
            plugin_records=list(installed.values()),
        )
    except ApplicationError as exc:
        response.issues = list(dict.fromkeys([*response.issues, exc.code]))
        return response
    except (ValidationError, ValueError):
        response.issues.append("binding_invalid")
        return response
    value = binding_value(
        compiled.content_hash,
        workflow_key,
        parameters,
        models,
        resources,
        [item.model_dump(mode="json", by_alias=True) for item in releases],
    )
    response.ready = True
    response.binding_token = canonical_digest(value)
    if source_run_id is not None:
        # The optional source is a comparison only; it never selects another package or input.
        original = service.store.get_run(source_run_id)
        if original is None:
            raise ApplicationError("run_not_found", "Run is unavailable", status=404)
        if (original.package_key, original.workflow_key) != (package_key, workflow_key):
            raise ApplicationError(
                "source_task_mismatch", "Source run belongs to a different task", status=409
            )
        previous = spec_bindings(original.spec)
        response.previous_bindings = {
            key: previous[key] for key in ("models", "resources", "plugins")
        }
        response.changed_bindings = [
            key for key in ("models", "resources", "plugins") if previous[key] != value[key]
        ]
    return response

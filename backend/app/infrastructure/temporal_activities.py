"""Durable I/O boundaries for DAG mappings and execution projections."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.domain.compiler import compile_package
from app.domain.definitions import (
    AgentDefinition,
    DeterministicStrategy,
    ModelStrategy,
    PackageDefinition,
)
from app.domain.execution import ExecutionEvidence, ResolvedRunSpec
from app.domain.mappings import evaluate_condition, resolve_mapping
from app.domain.schema_contract import validate_value
from app.domain.tool_contracts import ToolInvocationContext
from app.infrastructure.temporal_payloads import pack_value, unpack_value
from app.infrastructure.temporal_ports import ArtifactValues, ExecutionProjection, ToolInvoker


class RuntimeActivities:
    def __init__(
        self,
        projection: ExecutionProjection,
        artifacts: ArtifactValues,
        invoke: ToolInvoker,
        core_artifact: str,
        verify_core: Callable[[], None],
    ) -> None:
        self.projection = projection
        self.artifacts = artifacts
        self.invoke = invoke
        self.core_artifact = core_artifact
        self.verify_core = verify_core

    def registrations(self) -> list[Callable[..., Any]]:
        return [
            self.prepare_run,
            self.prepare_node,
            self.project_node,
            self.project_agent,
            self.agent_prompt,
            self.validate_agent_output,
            self.deterministic_agent,
            self.finalize_run,
        ]

    def namespace(self, spec: ResolvedRunSpec, nodes: dict[str, Any]) -> dict[str, Any]:
        artifacts = self.artifacts
        return {
            "workflow": {"input": spec.parameters},
            "nodes": {
                key: {
                    "status": value["status"],
                    **(
                        {"output": unpack_value(artifacts, value["output"])}
                        if value["status"] == "succeeded"
                        else {}
                    ),
                }
                for key, value in nodes.items()
            },
        }

    @activity.defn
    async def prepare_run(self, payload: dict[str, Any]) -> None:
        spec = ResolvedRunSpec.model_validate(payload)
        compiled = compile_package(spec.definition)
        if compiled.content_hash != spec.package_hash or (
            compiled.plans[spec.workflow_key].model_dump(mode="json", by_alias=True) != spec.plan
        ):
            raise ApplicationError("snapshot_integrity_failed", non_retryable=True)
        try:
            await asyncio.to_thread(self.verify_core)
        except Exception:
            raise ApplicationError("core_artifact_unavailable", non_retryable=True) from None
        if spec.core_artifact != self.core_artifact:
            raise ApplicationError("core_artifact_mismatch", non_retryable=True)
        await asyncio.to_thread(self.projection.project_run, spec.run_id, "running")

    @activity.defn
    async def prepare_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        spec = ResolvedRunSpec.model_validate(payload["spec"])
        package = PackageDefinition.model_validate(spec.definition)
        definition = package.workflows[spec.workflow_key].nodes[payload["nodeId"]]
        values = self.namespace(spec, payload["nodes"])
        try:
            if definition.condition is not None and not evaluate_condition(
                definition.condition, values
            ):
                return {"status": "skipped"}
            node_input = resolve_mapping(definition.input_mapping, values)
            validate_value(package.agents[definition.uses].input_schema, node_input)
            return {"status": "ready", "input": pack_value(self.artifacts, node_input)}
        except ValueError:
            return {"status": "failed", "errorCode": "node_input_invalid"}

    @activity.defn
    async def project_node(self, payload: dict[str, Any]) -> None:
        spec = ResolvedRunSpec.model_validate(payload["spec"])
        await asyncio.to_thread(
            self.projection.record_evidence,
            ExecutionEvidence(
                id=f"{spec.run_id}:node:{payload['nodeId']}",
                run_id=spec.run_id,
                node_id=payload["nodeId"],
                kind="node",
                status=payload["status"],
                input=payload.get("input"),
                output=payload.get("output"),
                error_code=payload.get("errorCode"),
                started_at=(
                    datetime.fromisoformat(payload["startedAt"])
                    if payload.get("startedAt")
                    else None
                ),
                finished_at=datetime.now(UTC) if payload["status"] != "running" else None,
                metadata={
                    "agentKey": PackageDefinition.model_validate(spec.definition)
                    .workflows[spec.workflow_key]
                    .nodes[payload["nodeId"]]
                    .uses
                },
            ),
        )

    @activity.defn
    async def project_agent(self, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(
            self.projection.record_evidence,
            ExecutionEvidence(
                id=payload["invocationId"],
                run_id=payload["runId"],
                node_id=payload["nodeId"],
                parent_id=f"{payload['runId']}:node:{payload['nodeId']}",
                kind="agent",
                status=payload["status"],
                attempt=payload["attempt"],
                input=payload["input"],
                output=payload.get("output"),
                error_code=payload.get("errorCode"),
                started_at=datetime.fromisoformat(payload["startedAt"]),
                finished_at=datetime.now(UTC) if payload["status"] != "running" else None,
            ),
        )

    @activity.defn
    async def agent_prompt(self, payload: dict[str, Any]) -> str:
        agent = AgentDefinition.model_validate(payload["agent"])
        assert isinstance(agent.strategy, ModelStrategy)
        value = unpack_value(self.artifacts, payload["input"])
        return json.dumps(
            {
                "instructions": agent.strategy.prompt,
                "input": value,
                "outputContract": agent.output_schema,
                "responseInstructions": (
                    "Return exactly one JSON value matching outputContract, without Markdown "
                    "fences or surrounding text. Preserve the declared root type: for string, "
                    "return a quoted JSON string; for array, return a JSON array; for object, "
                    "return a JSON object; for integer or number, return a JSON number; for "
                    "boolean, return true or false; for null, return null. Schema title and "
                    "description are labels and documentation, not object property names. "
                    "Do not invent an object wrapper or property from those labels."
                ),
            },
            ensure_ascii=False,
        )

    @activity.defn
    async def validate_agent_output(self, payload: dict[str, Any]) -> Any:
        definition = AgentDefinition.model_validate(payload["agent"])
        try:
            value = json.loads(payload["text"]) if "text" in payload else payload["output"]
            validate_value(definition.output_schema, value)
        except ValueError:
            raise ApplicationError("agent_output_invalid", non_retryable=True) from None
        return pack_value(self.artifacts, value)

    @activity.defn
    async def deterministic_agent(self, payload: dict[str, Any]) -> Any:
        async def beat() -> None:
            while True:
                activity.heartbeat()
                await asyncio.sleep(1)

        heartbeat = asyncio.create_task(beat())
        try:
            return await self.execute_deterministic(payload)
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def execute_deterministic(self, payload: dict[str, Any]) -> Any:
        definition = AgentDefinition.model_validate(payload["agent"])
        strategy = definition.strategy
        assert isinstance(strategy, DeterministicStrategy)
        value = unpack_value(self.artifacts, payload["input"])
        arguments = resolve_mapping(strategy.input_mapping, {"agent": {"input": value}})
        result = await self.invoke(
            payload,
            strategy.tool_id,
            arguments,
            ToolInvocationContext(
                run_id=payload["runId"],
                node_id=payload["nodeId"],
                invocation_id=payload["invocationId"],
                operation_id=payload["invocationId"] + ":tool:deterministic",
                deadline=datetime.fromisoformat(payload["deadline"]),
                tool_grants=tuple(definition.tools),
                resource_grants=tuple(definition.resources),
                cache_policy=definition.tool_cache.get(strategy.tool_id),
                resource_bindings={
                    key: payload["resourceBindings"][key] for key in definition.resources
                },
            ),
        )
        if result.status != "succeeded":
            raise ApplicationError(result.code or "tool_failed", non_retryable=True) from None
        output = resolve_mapping(
            strategy.output_mapping, {"tool": {"output": result.output}, "agent": {"input": value}}
        )
        validate_value(definition.output_schema, output)
        return pack_value(self.artifacts, output)

    @activity.defn
    async def finalize_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        spec = ResolvedRunSpec.model_validate(payload["spec"])
        status, output, error = payload["status"], None, payload.get("errorCode")
        if status == "succeeded":
            definition = PackageDefinition.model_validate(spec.definition).workflows[
                spec.workflow_key
            ]
            try:
                output = resolve_mapping(
                    definition.output_mapping, self.namespace(spec, payload["nodes"])
                )
                validate_value(definition.output_schema, output)
                output = pack_value(self.artifacts, output)
            except ValueError:
                status, error = "failed", "workflow_output_invalid"
        await asyncio.to_thread(self.projection.project_run, spec.run_id, status, output, error)
        return {"status": status, "output": output, "errorCode": error}

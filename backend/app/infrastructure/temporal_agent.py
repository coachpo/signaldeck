"""One bounded Agent contract with durable model and deterministic strategies."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Literal, cast

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import RunContext, ToolDefinition
from pydantic_ai.toolsets import AbstractToolset, DynamicToolset, ToolsetTool
from pydantic_ai.usage import UsageLimits
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError, is_cancelled_exception

with workflow.unsafe.imports_passed_through():
    from app.domain.schema_contract import validate_value
    from app.domain.tool_contracts import PluginRelease, ToolCatalog, ToolInvocationContext
    from app.infrastructure.temporal_cancellation import await_cancel_once
    from app.infrastructure.temporal_failures import failure_code
    from app.infrastructure.temporal_ports import ToolInvoker


class ContractValidator:
    def __init__(self, schema: dict[str, Any]):
        self.schema = schema

    def validate_python(
        self,
        input: Any,
        *,
        allow_partial: Literal["off", "on", "trailing-strings"] | bool = False,
        **kwargs: Any,
    ) -> Any:
        validate_value(self.schema, input)
        return input

    def validate_json(
        self,
        input: str | bytes | bytearray,
        *,
        allow_partial: Literal["off", "on", "trailing-strings"] | bool = False,
        **kwargs: Any,
    ) -> Any:
        import json

        return self.validate_python(json.loads(input))


class FrozenToolset(AbstractToolset[dict[str, Any]]):
    def __init__(self, invoke: ToolInvoker | None):
        self.invoke = invoke

    @property
    def id(self) -> str:
        return "frozen-gateway"

    async def get_tools(
        self, ctx: RunContext[dict[str, Any]]
    ) -> dict[str, ToolsetTool[dict[str, Any]]]:
        catalog = ToolCatalog(
            tuple(PluginRelease.model_validate(item) for item in ctx.deps["pluginReleases"])
        )
        definition = ctx.deps["agent"]
        result = {}
        for item in catalog.model_tools(tuple(definition["tools"])):
            _, contract = catalog.binding(catalog.resolve_alias(item["name"]))
            result[item["name"]] = ToolsetTool(
                toolset=self,
                tool_def=ToolDefinition(
                    name=item["name"],
                    description=item["description"],
                    parameters_json_schema=item["parameters"],
                ),
                max_retries=0,
                args_validator=ContractValidator(contract.input_schema),
            )
        return result

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[dict[str, Any]],
        tool: ToolsetTool[dict[str, Any]],
    ) -> Any:
        definition = ctx.deps["agent"]
        tool_id = ctx.deps["toolAliases"].get(name)
        if tool_id is None:
            raise ApplicationError("tool_alias_invalid", non_retryable=True)
        context = ToolInvocationContext(
            run_id=ctx.deps["runId"],
            node_id=ctx.deps["nodeId"],
            invocation_id=ctx.deps["invocationId"],
            operation_id=f"{ctx.deps['invocationId']}:tool:{ctx.run_step}:{ctx.tool_call_id}",
            deadline=datetime.fromisoformat(ctx.deps["deadline"]),
            tool_grants=tuple(definition["tools"]),
            resource_grants=tuple(definition["resources"]),
            cache_policy=definition.get("toolCache", {}).get(tool_id),
            resource_bindings={
                key: ctx.deps["resourceBindings"][key] for key in definition["resources"]
            },
        )
        if self.invoke is None:
            raise RuntimeError("Tool I/O is registered on the worker, not the workflow definition")
        result = await self.invoke(ctx.deps, tool_id, tool_args, context)
        if result.status != "succeeded":
            raise ApplicationError(result.code or "tool_failed", non_retryable=True)
        return result.output


class ToolsetFactory:
    def __init__(self, invoke: ToolInvoker | None):
        self.invoke = invoke

    def __call__(self, ctx: RunContext[dict[str, Any]]) -> FrozenToolset:
        return FrozenToolset(self.invoke)


class ToolConcurrency(AbstractCapability[dict[str, Any]]):
    semaphore: asyncio.Semaphore

    async def for_run(self, ctx: RunContext[dict[str, Any]]) -> ToolConcurrency:
        bound = ToolConcurrency()
        bound.semaphore = asyncio.Semaphore(ctx.deps["agent"]["budget"]["maxParallelTools"])
        return bound

    async def wrap_tool_execute(
        self, ctx: RunContext, *, call: Any, tool_def: Any, args: Any, handler: Any
    ) -> Any:
        async with self.semaphore:
            return await handler(args)


def model_settings(ctx: RunContext[dict[str, Any]]) -> ModelSettings:
    deps = ctx.deps
    strategy = deps["agent"]["strategy"]
    budget = deps["agent"]["budget"]
    remaining = budget["maxTokens"] - ctx.usage.total_tokens
    output_limit = max(1, remaining)
    if "maxOutputTokens" in budget:
        if remaining <= 0:
            raise UsageLimitExceeded("Agent token budget exhausted")
        output_limit = min(remaining, budget["maxOutputTokens"])
    return cast(
        ModelSettings,
        {
            "max_tokens": output_limit,
            "signaldeck_context": {
                "runId": deps["runId"],
                "nodeId": deps["nodeId"],
                "invocationId": deps["invocationId"],
                "modelCallId": f"{deps['invocationId']}:model:{ctx.run_step}",
                "resourceId": strategy["modelRef"],
                "binding": deps["modelBinding"],
                "deadline": deps["deadline"],
            },
        },
    )


WAIT_FOR_ACTIVITY_CANCEL = workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED


def create_agent(model: Model, invoke: ToolInvoker | None) -> Agent[dict[str, Any], str]:

    return Agent(
        model,
        name="signaldeck",
        deps_type=dict[str, Any],
        retries=0,
        toolsets=[DynamicToolset(ToolsetFactory(invoke), id="gateway")],
        model_settings=model_settings,
        capabilities=[
            ToolConcurrency(),
            TemporalDurability(
                activity_config={
                    "start_to_close_timeout": timedelta(hours=1),
                    "heartbeat_timeout": timedelta(seconds=5),
                    "retry_policy": RetryPolicy(
                        initial_interval=timedelta(seconds=1), maximum_attempts=3
                    ),
                    "cancellation_type": WAIT_FOR_ACTIVITY_CANCEL,
                }
            ),
        ],
    )


class WorkflowModel(Model):
    """The stable workflow registration shape has no provider or persistence capability."""

    @property
    def model_name(self) -> str:
        return "signaldeck-model-gateway"

    @property
    def system(self) -> str:
        return "signaldeck"

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        raise RuntimeError("Model I/O is registered on the worker, not the workflow definition")


WORKFLOW_AGENT = create_agent(WorkflowModel(), None)


async def io(
    name: str,
    payload: dict[str, Any],
    *,
    timeout: float = 30,
    complete_on_cancel: bool = False,
) -> Any:
    handle = workflow.start_activity(
        name,
        payload,
        start_to_close_timeout=timedelta(seconds=timeout),
        heartbeat_timeout=timedelta(seconds=3) if name == "deterministic_agent" else None,
        retry_policy=RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=3),
        cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
    )
    return await await_cancel_once(handle, cancel_handle=not complete_on_cancel)


@workflow.defn
class AgentWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        definition = payload["agent"]
        result: dict[str, Any]
        deadline_timeout: asyncio.Timeout | None = None
        try:
            remaining = (
                datetime.fromisoformat(payload["deadline"]) - workflow.now()
            ).total_seconds()
            if remaining <= 0:
                raise TimeoutError
            deadline_timeout = asyncio.timeout(remaining)
            async with deadline_timeout:
                await io("project_agent", {**payload, "status": "running"})
                if definition["strategy"]["kind"] == "deterministic":
                    output = await io("deterministic_agent", payload, timeout=remaining)
                else:
                    prompt = await io("agent_prompt", payload)
                    budget = definition["budget"]
                    response = await await_cancel_once(
                        asyncio.create_task(
                            WORKFLOW_AGENT.run(
                                prompt,
                                deps=payload,
                                usage_limits=UsageLimits(
                                    request_limit=budget["maxModelRequests"],
                                    tool_calls_limit=budget["maxToolCalls"],
                                    total_tokens_limit=budget["maxTokens"],
                                ),
                            )
                        )
                    )
                    output = await io("validate_agent_output", {**payload, "text": response.output})
                result = {"status": "succeeded", "output": output}
            if deadline_timeout.expired():
                result = {"status": "timed_out", "errorCode": "agent_deadline_exceeded"}
        except TimeoutError:
            result = {"status": "timed_out", "errorCode": "agent_deadline_exceeded"}
        except asyncio.CancelledError:
            result = (
                {"status": "timed_out", "errorCode": "agent_deadline_exceeded"}
                if deadline_timeout is not None and deadline_timeout.expired()
                else {"status": "cancelled", "errorCode": "cancelled"}
            )
        except Exception as exc:
            # Temporal can replace asyncio cancellation with an ActivityError cause.
            # The local timeout state keeps deadline expiry distinct from user cancellation.
            if deadline_timeout is not None and deadline_timeout.expired():
                result = {"status": "timed_out", "errorCode": "agent_deadline_exceeded"}
            elif is_cancelled_exception(exc):
                result = {"status": "cancelled", "errorCode": "cancelled"}
            elif workflow.now() >= datetime.fromisoformat(payload["deadline"]):
                result = {"status": "timed_out", "errorCode": "agent_deadline_exceeded"}
            else:
                result = {
                    "status": "failed",
                    "errorCode": failure_code(exc, "agent_execution_failed"),
                }
        # Terminal evidence confirms completed work even if cancellation arrives during commit.
        await io("project_agent", {**payload, **result}, complete_on_cancel=True)
        return result

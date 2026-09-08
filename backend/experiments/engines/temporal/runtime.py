"""Temporal candidate execution boundary; fake I/O is recorded outside history."""

import asyncio
import hashlib
import json
import os
import time
from datetime import timedelta
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import PydanticAIWorkflow, TemporalDurability
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset, DynamicToolset, ToolsetTool
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError


def record(event, **data):
    line = json.dumps(dict(event=event, at=time.time(), **data)) + "\n"
    fd = os.open(os.environ["PROBE_LOG"], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode())
    finally:
        os.close(fd)


class SchemaValidator:
    def __init__(self, schema):
        self.validator = Draft202012Validator(schema)

    def validate_python(self, value, **kwargs):
        self.validator.validate(value)
        if set(value) - set(self.validator.schema.get("properties", {})):
            raise ValueError("undeclared property")
        return value

    def validate_json(self, value, **kwargs):
        return self.validate_python(json.loads(value))


class Gateway(AbstractToolset[dict]):
    @property
    def id(self):
        return "gateway"

    async def get_tools(self, ctx):
        return {
            item["alias"]: ToolsetTool(
                toolset=self,
                tool_def=ToolDefinition(name=item["alias"], parameters_json_schema=item["schema"]),
                max_retries=0,
                args_validator=SchemaValidator(item["schema"]),
            )
            for item in ctx.deps["tools"]
        }

    async def call_tool(self, name, tool_args, ctx, tool):
        deps = ctx.deps
        item = next(t for t in deps["tools"] if t["alias"] == name)
        if item["id"] not in deps["grants"]:
            raise ApplicationError("grant denied", non_retryable=True)
        for identity in [deps["core"], item["artifact"]]:
            path = Path(os.environ["PROBE_ARTIFACTS"]) / identity
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != identity:
                raise ApplicationError(
                    "frozen artifact unavailable: " + identity, non_retryable=True
                )
        record(
            "tool",
            run=deps["run"],
            tool=item["id"],
            args=tool_args,
            artifact=item["artifact"],
            attempt=activity.info().attempt,
        )
        return {
            "run": deps["run"],
            "tool": item["id"],
            "value": tool_args["value"],
            "artifact": item["artifact"],
        }


def gateway(ctx):
    return Gateway()


async def fake_model(messages, info):
    prompt = next(p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart))
    spec = json.loads(prompt)
    returns = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
    step = len(returns)
    record(
        "model",
        run=spec["run"],
        step=step,
        tools=[t.name for t in info.function_tools],
        schemas=[t.parameters_json_schema for t in info.function_tools],
        attempt=activity.info().attempt,
    )
    if step == 1 and spec.get("pause"):
        try:
            while not (Path(os.environ["PROBE_ARTIFACTS"]) / "release").exists():
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            record("model-cancelled", run=spec["run"], step=step)
            raise
    if step < 2:
        tool = info.function_tools[step % len(info.function_tools)]
        return ModelResponse(
            parts=[ToolCallPart(tool.name, {"value": spec["value"]}, tool_call_id=f"call-{step}")]
        )
    return ModelResponse(parts=[TextPart(json.dumps([p.content for p in returns]))])


agent = Agent(
    FunctionModel(fake_model, model_name="fake"),
    name="probe",
    deps_type=dict,
    toolsets=[DynamicToolset(gateway, id="gateway")],
    capabilities=[
        TemporalDurability(
            activity_config={
                "start_to_close_timeout": timedelta(seconds=30),
                "heartbeat_timeout": timedelta(seconds=2),
                "retry_policy": RetryPolicy(
                    initial_interval=timedelta(seconds=0.1), maximum_attempts=3
                ),
            }
        )
    ],
)


@workflow.defn
class AgentWorkflow(PydanticAIWorkflow):
    __pydantic_ai_agents__ = [agent]

    @workflow.run
    async def run(self, spec: dict) -> str:
        result = await agent.run(json.dumps(spec), deps=spec)
        return result.output


@activity.defn
async def node(spec: dict) -> str:
    record("node-start", run=spec["run"], node=spec["node"])
    try:
        until = time.monotonic() + spec["delay"]
        while time.monotonic() < until:
            activity.heartbeat()
            await asyncio.sleep(0.05)
        record("node-end", run=spec["run"], node=spec["node"])
        return spec["node"]
    except asyncio.CancelledError:
        record("node-cancelled", run=spec["run"], node=spec["node"])
        raise


@workflow.defn
class GraphWorkflow:
    @workflow.run
    async def run(self, spec: dict) -> list[str]:
        async def execute(name, delay):
            return await workflow.execute_activity(
                node,
                dict(run=spec["run"], node=name, delay=delay),
                start_to_close_timeout=timedelta(seconds=30),
                heartbeat_timeout=timedelta(seconds=1),
                cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            )

        if spec.get("cancel"):
            await execute("A", 20)
            return [await execute("B", 0)]
        await execute("A", 0.05)

        async def fast():
            await execute("B", 0.1)
            return await execute("E", 0.05)

        result = await asyncio.gather(fast(), execute("C", 1))
        result.append(await execute("D", 0.05))
        return result


@workflow.defn
class RecoveryWorkflow:
    @workflow.run
    async def run(self, spec: dict) -> str:
        sibling = workflow.start_activity(
            node,
            dict(run=spec["run"], node="sibling", delay=0.01),
            start_to_close_timeout=timedelta(seconds=30),
        )
        child = await workflow.start_child_workflow(
            AgentWorkflow.run, spec, id=spec["run"] + "-agent"
        )
        await sibling
        return await child

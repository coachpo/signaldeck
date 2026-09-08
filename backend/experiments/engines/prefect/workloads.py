"""Real Prefect/Pydantic AI workloads for the isolated engine comparison."""

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from jsonschema import validate
from prefect import flow, task
from prefect.cache_policies import INPUTS, RUN_ID, TASK_SOURCE
from pydantic_ai import Agent
from pydantic_ai.durable_exec.prefect import PrefectDurability
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import Tool
from pydantic_ai.toolsets import DynamicToolset, FunctionToolset

ROOT = Path(os.environ["SD_PREFECT_PROBE_ROOT"])


def event(kind, **data):
    with (ROOT / "events.jsonl").open("a") as stream:
        stream.write(
            json.dumps({"kind": kind, "time": time.time(), "pid": os.getpid(), **data}) + "\n"
        )


def require_artifacts(spec):
    for role in ("core", "plugin"):
        digest = spec[role]
        path = ROOT / "artifacts" / digest
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Missing frozen {role} artifact: {digest}")


def dynamic_tools(ctx):
    spec = ctx.deps
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string", "enum": [spec["value"]]}},
        "required": ["value"],
        "additionalProperties": False,
    }

    async def gateway(ctx, **arguments):
        validate(arguments, schema)
        require_artifacts(spec)
        event(
            "tool",
            run=spec["run"],
            tool=spec["tool"],
            operation=ctx.tool_call_id,
            arguments=arguments,
            plugin=spec["plugin"],
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(ROOT / "artifacts" / spec["plugin"]),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        output, _ = await process.communicate(json.dumps(arguments).encode())
        if process.returncode != 0:
            raise RuntimeError("frozen plugin process failed")
        return {**json.loads(output), "plugin": spec["plugin"]}

    tool = Tool.from_schema(
        gateway,
        name=spec["tool"],
        description="Frozen dynamic tool",
        json_schema=schema,
        takes_ctx=True,
    )
    return FunctionToolset([tool], id="resolved-plugin")


async def fake_model(messages, info):
    spec = json.loads(messages[0].parts[0].content)
    returned = [
        part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)
    ]
    event(
        "model", run=spec["run"], round=len(returned), tools=[t.name for t in info.function_tools]
    )
    assert [t.name for t in info.function_tools] == [spec["tool"]]
    assert info.function_tools[0].parameters_json_schema["properties"]["value"]["enum"] == [
        spec["value"]
    ]
    if not returned:
        if spec["run"].startswith("parallel-"):
            (ROOT / spec["run"]).write_text("entered")
            async with asyncio.timeout(20):
                while len(list(ROOT.glob("parallel-*"))) < 2:
                    await asyncio.sleep(0.02)
        return ModelResponse(
            parts=[ToolCallPart(spec["tool"], {"value": spec["value"]}, tool_call_id="operation-1")]
        )
    if spec.get("crash") and not (ROOT / "release").exists():
        (ROOT / "confirmed").write_text(spec["run"])
        while not (ROOT / "release").exists():
            await asyncio.sleep(0.05)
    if len(returned) == 1:
        return ModelResponse(
            parts=[ToolCallPart(spec["tool"], {"value": spec["value"]}, tool_call_id="operation-2")]
        )
    return ModelResponse(parts=[TextPart(json.dumps(returned[-1].content))])


agent = Agent(
    FunctionModel(fake_model),
    name="probe-agent",
    toolsets=[DynamicToolset(dynamic_tools, id="gateway")],
    capabilities=[PrefectDurability()],
)


@flow(name="sd-prefect-agent", persist_result=True, retries=1)
async def agent_flow(spec: dict) -> str:
    # Platform responsibility: reject missing bound artifacts before any cached replay.
    require_artifacts(spec)
    result, _ = await asyncio.gather(
        agent.run(json.dumps(spec), deps=spec),
        node(spec["run"], "successful-sibling", 0.03, []),
    )
    event("agent_complete", run=spec["run"], output=result.output)
    return result.output


@task(persist_result=True, cache_policy=INPUTS + RUN_ID + TASK_SOURCE)
async def node(run: str, name: str, delay: float, dependencies: list):
    event("node_start", run=run, node=name)
    await asyncio.sleep(delay)
    event("node_end", run=run, node=name)
    return name


@flow(name="sd-prefect-dag")
async def dag_flow(run: str):
    a = await node(run, "A", 0.05, [])

    async def left():
        b = await node(run, "B", 0.10, [a])
        return await node(run, "E", 0.05, [b])

    async def right():
        return await node(run, "C", 1.0, [a])

    e, c = await asyncio.gather(left(), right())
    return await node(run, "D", 0.01, [e, c])


@flow(name="sd-prefect-cancel")
async def cancel_flow():
    try:
        event("cancel_started")
        await asyncio.sleep(120)
        event("forbidden_downstream")
    finally:
        event("cancel_propagated")


@flow(name="sd-prefect-deadline", retries=2, retry_delay_seconds=0)
async def deadline_flow(deadline: float):
    # Prefect per-attempt timeouts alone do not represent the frozen total deadline.
    remaining = deadline - time.time()
    event("deadline_attempt", remaining=remaining)
    if remaining <= 0:
        raise TimeoutError("frozen total deadline expired")
    async with asyncio.timeout(remaining):
        await asyncio.sleep(10)

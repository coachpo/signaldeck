"""Isolated Hatchet candidate probe, not SignalDeck acceptance tests."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from hatchet_sdk import ClientConfig, Context, DurableContext, Hatchet, TTLBasedIdempotencyConfig
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models import Model

ROOT = Path(os.environ.get("SD_HATCHET_STATE", "/tmp/signaldeck-hatchet-evidence"))
CLIENT = Path(os.environ.get("SD_HATCHET_CLIENT", "/tmp/signaldeck-hatchet-client.json"))
hatchet = Hatchet(config=ClientConfig.model_validate_json(CLIENT.read_text()))


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run: str
    branch: str = "B"
    kind: str = "node"
    round: int = 0
    alias: str = "plugin_one__lookup"
    value: str = "one"
    artifact: str = "core-v1_plugin-v1"
    pause: bool = False
    delay: float = 0
    deadline: float = 0
    schemas: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []


def event(i: Input, name: str, **extra: Any) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    record = {
        "run": i.run,
        "branch": i.branch,
        "event": name,
        "time": time.time(),
        "pid": os.getpid(),
        **extra,
    }
    with (ROOT / "events.jsonl").open("a") as stream:
        stream.write(json.dumps(record) + "\n")


def pinned(i: Input) -> None:
    if not (ROOT / i.artifact).is_file():
        event(i, "boundary-rejected", reason="PINNED_ARTIFACT_MISSING")
        raise ValueError("PINNED_ARTIFACT_MISSING")
    if i.deadline and time.time() >= i.deadline:
        event(i, "boundary-rejected", reason="TOTAL_DEADLINE_EXCEEDED")
        raise ValueError("TOTAL_DEADLINE_EXCEEDED")


@hatchet.task(
    name="sd-hatchet-call",
    input_validator=Input,
    retries=2,
    execution_timeout=timedelta(seconds=40),
)
async def call(i: Input, ctx: Context) -> dict[str, Any]:
    pinned(i)
    event(i, f"{i.kind}-start", round=i.round)
    try:
        if i.kind == "model":
            if i.round == 1 and i.pause:
                while not (ROOT / (i.run + "-release")).exists():
                    await asyncio.sleep(0.1)
            if i.round == 0:
                expected = i.alias
                assert [s["name"] for s in i.schemas] == [expected]
                schema = i.schemas[0]["schema"]
                assert schema["properties"]["value"]["const"] == i.value
                response = ModelResponse(
                    parts=[ToolCallPart(expected, {"value": i.value}, tool_call_id="lookup")]
                )
            else:
                messages = ModelMessagesTypeAdapter.validate_python(i.messages)
                values = [
                    p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart)
                ]
                assert len(values) == 1
                response = ModelResponse(parts=[TextPart(json.dumps(values[0]))])
            event(i, "model-confirmed", round=i.round)
            return {"messages": json.loads(ModelMessagesTypeAdapter.dump_json([response]))}
        if i.kind == "tool":
            assert i.alias in ("plugin_one__lookup", "plugin_two__lookup")
            Draft202012Validator(i.schemas[0]["schema"]).validate({"value": i.value})
            await asyncio.sleep(i.delay)
            value = {
                "value": i.value,
                "plugin": i.alias,
                "artifact": i.artifact,
                "fresh": time.time_ns(),
            }
            event(i, "tool-confirmed", value=value)
            return value
        await asyncio.sleep(i.delay)
        event(i, "node-confirmed")
        return {"branch": i.branch}
    except asyncio.CancelledError:
        event(i, "actual-cancelled", kind=i.kind)
        raise


class DurableModel(Model):
    def __init__(self, spec: Input):
        super().__init__()
        self.spec = spec
        self.round = 0

    @property
    def model_name(self) -> str:
        return "hatchet-fake-pinned"

    @property
    def system(self) -> str:
        return "fake"

    async def request(self, messages, model_settings, model_request_parameters):
        number = self.round
        self.round += 1
        data = self.spec.model_copy(
            update={
                "kind": "model",
                "round": number,
                "messages": json.loads(ModelMessagesTypeAdapter.dump_json(messages)),
                "schemas": [
                    {"name": t.name, "schema": t.parameters_json_schema}
                    for t in model_request_parameters.function_tools
                ],
            }
        )
        out = await call.aio_run(data, child_key=f"{self.spec.branch}-model-{number}")
        return ModelMessagesTypeAdapter.validate_python(out["messages"])[0]


async def agent_run(i: Input) -> str:
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string", "const": i.value}},
        "required": ["value"],
        "additionalProperties": False,
    }

    async def gateway(**arguments):
        Draft202012Validator(schema).validate(arguments)
        return await call.aio_run(
            i.model_copy(update={"kind": "tool", "schemas": [{"name": i.alias, "schema": schema}]}),
            child_key=f"{i.branch}-tool-0",
        )

    tool = Tool.from_schema(gateway, i.alias, "Frozen qualified lookup", schema)
    result = await Agent(DurableModel(i), tools=[tool]).run("Look up the declared resource")
    return result.output


@hatchet.durable_task(
    name="sd-hatchet-agent",
    input_validator=Input,
    retries=2,
    execution_timeout=timedelta(seconds=120),
)
async def durable_agent(i: Input, ctx: DurableContext) -> dict[str, Any]:
    result = await agent_run(i)
    return {"result": result, "attempt": ctx.attempt_number}


@hatchet.durable_task(
    name="sd-hatchet-dag",
    input_validator=Input,
    retries=2,
    execution_timeout=timedelta(seconds=120),
    idempotency=TTLBasedIdempotencyConfig(key_expression="input.run", ttl=timedelta(hours=24)),
)
async def dag(i: Input, ctx: DurableContext) -> dict[str, Any]:
    await call.aio_run(i.model_copy(update={"branch": "A"}), child_key="A")

    async def b_then_e():
        b = await call.aio_run(i.model_copy(update={"branch": "B", "delay": 0.2}), child_key="B")
        e = await call.aio_run(i.model_copy(update={"branch": "E"}), child_key="E")
        return b, e

    b, c = await asyncio.gather(
        b_then_e(), call.aio_run(i.model_copy(update={"branch": "C", "delay": 2}), child_key="C")
    )
    d = await call.aio_run(i.model_copy(update={"branch": "D"}), child_key="D")
    return {"B": b, "C": c, "D": d}


if __name__ == "__main__":
    import sys

    durable = sys.argv[1] == "durable"
    worker = hatchet.worker(
        "sd-hatchet-" + sys.argv[1],
        slots=12,
        durable_slots=12,
        workflows=[durable_agent, dag] if durable else [call],
    )
    worker.start()

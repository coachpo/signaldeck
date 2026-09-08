"""A separately hosted synchronous effect using the distributed plugin transport."""

import json
import os
import time
from pathlib import Path

import anyio
from plugin_runtime.server import application

STATE = Path(os.environ["HELD_PLUGIN_STATE"])
BINDING = json.loads((STATE / "release.json").read_text())


def record(name, value):
    path = STATE / name
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


def execute(name, arguments, context):
    operation = context["operationId"]
    record("started.json", {"operationId": operation, "input": arguments})
    expires = time.monotonic() + 40
    while not (STATE / "release").exists():
        if os.environ.get("HELD_PLUGIN_COOPERATIVE") == "1":
            try:
                anyio.from_thread.check_cancelled()
            except BaseException:
                record("cancelled.json", {"operationId": operation})
                raise
        if time.monotonic() >= expires:
            raise RuntimeError("Test fixture was not released")
        time.sleep(0.01)
    output = {**arguments, "value": arguments["value"] + 1}
    record("effect.json", {"operationId": operation, "output": output})
    return output


def query(operation_id, resources, grants):
    effect = STATE / "effect.json"
    if effect.exists():
        result = json.loads(effect.read_text())
        if result["operationId"] == operation_id:
            return {"status": "succeeded", "output": result["output"]}
    return {"status": "unknown"}


runtime = application(BINDING, execute, query)


async def app(scope, receive, send):
    """Observe protocol requests without changing the actual runtime handlers."""
    body = bytearray()

    async def observed_receive():
        message = await receive()
        if message["type"] == "http.request":
            body.extend(message.get("body", b""))
            if not message.get("more_body", False) and body:
                with (STATE / "requests.jsonl").open("a") as stream:
                    stream.write(body.decode() + "\n")
        return message

    await runtime(scope, observed_receive, send)

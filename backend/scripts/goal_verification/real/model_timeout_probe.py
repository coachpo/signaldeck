"""A real model reply can be unknown without implying any external save."""

import json
import os
import time
from pathlib import Path

from acceptance import limit_package, save
from probe import OUT, launch, request

provider = json.loads((Path.home() / ".pi/agent/models.json").read_text())["providers"]["prism"]
key = provider["apiKey"]
key = os.environ.get(key, key)
request(
    "/resources",
    {
        "resourceId": "timeout-model",
        "kind": "model",
        "config": {
            "name": "真实回复延迟验证",
            "baseUrl": "http://127.0.0.1:4375/v1",
            "modelId": "glm-5.3-flash",
            "apiStyle": "chat_completions",
            "timeoutSeconds": 1,
            "providerCapabilities": {"outputTokenLimitParameter": "max_tokens"},
        },
        "credentials": {"apiKey": key},
    },
)
record = limit_package("gaps_model_timeout", 16)
definition = record["definition"]
definition["agents"]["writer"]["strategy"]["modelRef"] = "timeout-model"
definition["agents"]["writer"]["budget"]["deadlineSeconds"] = 2
definition["workflows"]["run"]["deadlineSeconds"] = 15
request(
    "/workflow-packages/gaps_model_timeout",
    {"manifestSource": json.dumps(definition)},
    method="PATCH",
)
run = launch("gaps_model_timeout", "run", {}, "model-reply-timeout-no-write")
result = request("/runs/" + run["id"] + "/result")
save("model-timeout.json", {"run": run, "result": result})
assert run["status"] == "failed"
assert not any(e["kind"] == "tool" for e in run["evidence"])
assert any(e["kind"] == "model" and e["status"] == "unknown" for e in run["evidence"])
assert run["hasUnknownEffects"] is False and run["hasUnknownResults"] is True
assert result["unknownEvidenceIds"] == [] and result["readUnknownEvidenceIds"]
assert run["usageProjection"]["summary"]["outputTokens"] is None
deadline = time.monotonic() + 180
relay_file = OUT / "model-timeout-relay.jsonl"
while not relay_file.exists() or not relay_file.stat().st_size:
    if time.monotonic() >= deadline:
        raise TimeoutError("Real delayed provider response was not observed")
    time.sleep(0.2)
responses = [json.loads(line) for line in relay_file.read_text().splitlines()]
assert responses and all(row["httpStatus"] == 200 for row in responses)
assert all(row["max_tokens"] == 16 and row["usage"] for row in responses)
save("model-timeout.json", {"run": run, "result": result, "actualResponses": responses})
print("Verified genuine delayed model response remains unknown without a save warning.", flush=True)

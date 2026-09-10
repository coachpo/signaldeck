"""Repeatable public-API observations against an owned local test instance."""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

BASE = "http://127.0.0.1:8301/api"
OUT = Path(os.environ.get("GOAL_REAL_OUTPUT_DIR", Path(__file__).parent)).resolve()


def request(path, data=None, method=None, absolute=False):
    req = urllib.request.Request(
        path if absolute else BASE + path,
        data=None if data is None else json.dumps(data, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
        return json.loads(body) if body else None


def wait_run(rid, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = request("/runs/" + rid)
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(1)
    raise RuntimeError("Owned run did not reach a terminal state: " + rid)


def observations_for_run(run):
    path = OUT / "provider-observations.jsonl"
    all_events = (
        [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    )

    def seconds(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()

    start = seconds(run["createdAt"])
    finish = seconds(run["finishedAt"]) if run.get("finishedAt") else time.time()
    events = []
    for source in all_events:
        request_start = source.get(
            "requestStartedAt", source.get("timestamp", 0) - source.get("elapsedSeconds", 0)
        )
        if not start <= request_start <= finish:
            continue
        event = {**source, "requestStartedAtDerived": request_start}
        for attempt in run["evidence"]:
            if (
                attempt["kind"] != "attempt"
                or (attempt.get("metadata") or {}).get("networkKind") != "model_request"
            ):
                continue
            resource = (attempt.get("metadata") or {}).get("resourceId")
            if (
                run["spec"].get("modelBindings", {}).get(resource, {}).get("baseUrl")
                != "http://127.0.0.1:4374/provider/v1"
            ):
                continue
            if not attempt.get("startedAt"):
                continue
            attempt_start = seconds(attempt["startedAt"])
            attempt_end = seconds(attempt["finishedAt"]) if attempt.get("finishedAt") else finish
            if attempt_start <= request_start <= attempt_end:
                event["matchedAttemptId"] = attempt["id"]
                event["responseCompletedBeforeAttemptEnded"] = (
                    source.get("timestamp", 0) <= attempt_end
                )
                break
        if "matchedAttemptId" in event:
            events.append(event)
    return events


def compact(run, label):
    evidence = []
    for e in run["evidence"]:
        v = {
            k: e.get(k)
            for k in (
                "id",
                "parentId",
                "operationId",
                "nodeId",
                "kind",
                "toolId",
                "status",
                "errorCode",
                "startedAt",
                "finishedAt",
                "metadata",
            )
        }
        if e["kind"] == "model":
            output = e.get("output") or {}
            v["model"] = output.get("model_name")
            v["usage"] = output.get("usage")
            v["finishReason"] = output.get("finish_reason")
        elif e["kind"] == "tool":
            v["input"] = e.get("input")
            v["output"] = e.get("output")
        evidence.append(v)
    try:
        usage = request("/runs/" + run["id"] + "/usage")
    except urllib.error.HTTPError as exc:
        usage = {"httpStatus": exc.code}
    events = observations_for_run(run)
    return {
        "label": label,
        "providerObservations": events,
        **{
            k: run.get(k)
            for k in (
                "id",
                "title",
                "packageKey",
                "workflowKey",
                "packageHash",
                "status",
                "errorCode",
                "createdAt",
                "finishedAt",
                "origin",
                "output",
                "hasUnknownEffects",
                "hasUnknownResults",
            )
        },
        "spec": run["spec"],
        "coreArtifact": run["spec"]["coreArtifact"],
        "evidence": evidence,
        "usageProjection": usage,
    }


def record(run, label):
    path = OUT / "runs.json"
    rows = json.loads(path.read_text()) if path.exists() else []
    value = compact(run, label)
    rows.append(value)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "label": label,
                "id": run["id"],
                "status": run["status"],
                "errorCode": run.get("errorCode"),
                "models": [
                    {"status": e["status"], "errorCode": e.get("errorCode")}
                    for e in run["evidence"]
                    if e["kind"] == "model"
                ],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return value


def launch(package, workflow, parameters, label):
    p = request(
        "/workflow-packages/" + package + "/prepare",
        {"workflowKey": workflow, "parameters": parameters},
    )
    if not p["ready"]:
        raise RuntimeError("Preparation not ready: " + str(p["issues"]))
    r = request(
        "/workflow-packages/" + package + "/launches",
        {
            "workflowKey": workflow,
            "parameters": parameters,
            "launchId": str(uuid.uuid4()),
            "bindingToken": p["bindingToken"],
        },
    )
    return record(wait_run(r["id"]), label)


def configure(model_options=None):
    p = json.loads((Path.home() / ".pi/agent/models.json").read_text())["providers"]["prism"]
    key = p["apiKey"]
    if not isinstance(key, str) or not key or key.startswith("!"):
        raise RuntimeError("Credential needs unsupported resolution; value withheld")
    key = os.environ.get(key, key)
    assert any(m.get("id") == "glm-5.3-flash" for m in p["models"])
    release = request("http://127.0.0.1:21082/release", absolute=True)
    request("/plugins", {"release": release, "enabled": True})
    request(
        "/resources",
        {
            "resourceId": "notes-workspace",
            "kind": "tool",
            "config": {
                "name": "GLM真实复核笔记库",
                "pluginId": "example/notes",
                "scope": {"collection": "observed-gaps"},
            },
        },
    )
    request(
        "/resources",
        {
            "resourceId": "research-model",
            "kind": "model",
            "config": {
                "name": "GLM真实复核接口",
                "baseUrl": "http://127.0.0.1:4374/provider/v1",
                "modelId": "glm-5.3-flash",
                "apiStyle": "chat_completions",
                "timeoutSeconds": 90,
                **(model_options or {}),
            },
            "credentials": {"apiKey": key},
        },
    )
    print("Configured real glm-5.3-flash and actual Notes on owned databases.", flush=True)

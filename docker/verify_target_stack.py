"""Exercise an isolated local target stack through its public HTTP surfaces."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from ruamel.yaml import YAML


class Check:
    def __init__(self, base: str, finance: str):
        for url in (base, finance):
            if urlsplit(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("Acceptance endpoints must be local")
        self.base = base.rstrip("/")
        self.finance = finance.rstrip("/")
        self.client = httpx.Client(timeout=15)

    def request(self, path: str, payload=None, method="GET"):
        response = self.client.request(method, self.base + path, json=payload)
        if response.status_code >= 400:
            code = response.json().get("code", "request_failed")
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code} ({code})")
        return None if response.status_code == 204 else response.json()

    def wait_run(self, run_id: str):
        until = time.monotonic() + 240
        previous = None
        while time.monotonic() < until:
            run = self.request("/api/runs/" + run_id)
            if run["status"] != previous:
                print(f"Run {run_id}: {run['status']}", flush=True)
                previous = run["status"]
            if run["status"] in {"succeeded", "failed", "cancelled"}:
                if run["status"] != "succeeded":
                    codes = sorted({e["errorCode"] for e in run["evidence"] if e.get("errorCode")})
                    raise RuntimeError(f"Run failed: {run.get('errorCode')} / {codes}")
                return run
            time.sleep(0.5)
        raise RuntimeError("Run did not finish within the acceptance observation window")

    def artifact(self, ref):
        response = self.client.get(self.base + "/api/artifacts/" + ref["digest"])
        response.raise_for_status()
        assert len(response.content) == ref["sizeBytes"]
        assert "sha256:" + hashlib.sha256(response.content).hexdigest() == ref["digest"]
        return response.json()

    def value(self, value):
        return (
            self.artifact(value["$artifact"])
            if isinstance(value, dict) and "$artifact" in value
            else value
        )

    def launch(self, package_key, workflow, parameters, launch_id):
        payload = {"workflowKey": workflow, "parameters": parameters, "launchId": launch_id}
        run = self.request(f"/api/workflow-packages/{package_key}/launches", payload, "POST")
        repeated = self.request(f"/api/workflow-packages/{package_key}/launches", payload, "POST")
        assert repeated["id"] == run["id"]
        return self.wait_run(run["id"])


def references(value):
    found = []
    if isinstance(value, dict):
        if set(value) == {"$artifact"}:
            found.append(value["$artifact"])
        else:
            for child in value.values():
                found.extend(references(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(references(child))
    return found


def notes_package(suffix: str) -> dict:
    notes = YAML(typ="safe").load(
        (Path(__file__).resolve().parents[1] / "demo/research_notes.yaml").read_text()
    )
    notes["metadata"]["key"] = "compose-notes-" + suffix
    notes["agents"]["summarize"]["strategy"]["modelRef"] = "compose-model-" + suffix
    return notes


def finance_package(notes: dict, suffix: str) -> dict:
    finance = copy.deepcopy(notes)
    finance["metadata"]["key"] = "compose-finance-" + suffix
    report = finance["agents"].pop("write_note")
    report["tools"] = ["signaldeck/finance/reports_create"]
    report["resources"] = []
    report["inputSchema"] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 160},
            "content": {"type": "string", "minLength": 1},
        },
        "required": ["name", "content"],
    }
    report["outputSchema"] = {
        "type": "object",
        "properties": {"slug": {"type": "string"}},
        "required": ["slug"],
    }
    report["strategy"] = {
        "kind": "deterministic",
        "toolId": "signaldeck/finance/reports_create",
        "inputMapping": {"ref": "agent.input"},
        "outputMapping": {"object": {"slug": {"ref": "tool.output.slug"}}},
    }
    finance["agents"]["write_report"] = report
    finance["agents"]["summarize"]["outputSchema"]["properties"]["text"]["minLength"] = 1
    workflow = finance["workflows"]["research"]
    workflow["inputSchema"]["properties"]["title"]["maxLength"] = 160
    workflow["inputSchema"]["properties"]["text"]["minLength"] = 1
    workflow["outputSchema"] = report["outputSchema"]
    workflow["nodes"]["save"]["uses"] = "write_report"
    workflow["nodes"]["save"]["inputMapping"] = {
        "object": {
            "name": {"ref": "workflow.input.title"},
            "content": {
                "ref": "nodes.edit.output.text",
                "onMissing": {"ref": "workflow.input.text"},
            },
        }
    }
    finance["workflows"] = {"report": workflow}
    return finance


def execute(check: Check) -> dict:
    assert check.client.get(check.base + "/").status_code == 200
    assert check.client.get(check.finance + "/").status_code == 200
    until = time.monotonic() + 90
    expected = {"signaldeck/finance", "signaldeck/digital-oracle", "example/notes"}
    while time.monotonic() < until:
        plugins = check.request("/api/plugins")["items"]
        if expected.issubset({item["pluginId"] for item in plugins}):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("Local plugin bootstrap did not install all enabled plugins")
    suffix = uuid4().hex[:8]
    notes = notes_package(suffix)
    check.request(
        "/api/resources",
        {
            "resourceId": "compose-model-" + suffix,
            "kind": "model",
            "config": {
                "name": "Acceptance fake model",
                "baseUrl": "http://fake-model:8001/v1",
                "modelId": "fake-structured",
                "apiStyle": "chat_completions",
                "timeoutSeconds": 20,
            },
            "credentials": {"apiKey": "compose-fake-credential"},
        },
        "POST",
    )
    assert "compose-fake-credential" not in json.dumps(check.request("/api/resources"))
    check.request("/api/workflow-packages", {"manifestSource": json.dumps(notes)}, "POST")
    large_text = "Local Compose execution evidence. " * 2400
    captured = check.launch(
        notes["metadata"]["key"],
        "capture",
        {"title": "Compose capture " + suffix, "text": large_text},
        "capture-" + suffix,
    )
    assert check.value(captured["output"])["text"] == large_text
    artifact_refs = references(captured)
    assert artifact_refs, "Large execution values must use content-addressed references"
    for ref in artifact_refs:
        check.artifact(ref)
    model_run = check.launch(
        notes["metadata"]["key"],
        "research",
        {
            "title": "Compose edited " + suffix,
            "text": "A controlled test excerpt.",
            "query": "absent-" + suffix,
            "summarize": True,
        },
        "model-" + suffix,
    )
    assert any(e["kind"] == "model" and e["status"] == "succeeded" for e in model_run["evidence"])
    assert "fake" in check.value(model_run["output"])["text"]
    assert "compose-fake-credential" not in json.dumps(model_run)

    finance = finance_package(notes, suffix)
    check.request("/api/workflow-packages", {"manifestSource": json.dumps(finance)}, "POST")
    report_run = check.launch(
        finance["metadata"]["key"],
        "report",
        {
            "title": "Compose report " + suffix,
            "text": "Controlled research content.",
            "query": "absent-" + suffix,
            "summarize": True,
        },
        "report-" + suffix,
    )
    slug = check.value(report_run["output"])["slug"]
    saved = check.client.get(check.finance + "/api/reports/" + slug)
    saved.raise_for_status()
    assert saved.json()["source"] == "agent"
    assert saved.json()["metadata"]["createdBy"]["runId"] == report_run["id"]
    assert (
        check.client.patch(
            check.finance + "/api/reports/" + slug, json={"content": "overwrite"}
        ).status_code
        == 409
    )

    schedule = check.request(
        "/api/schedules",
        {
            "name": "Compose schedule " + suffix,
            "packageKey": notes["metadata"]["key"],
            "workflowKey": "capture",
            "parameters": {
                "title": "Scheduled note " + suffix,
                "text": "Explicit schedule trigger",
            },
            "cron": "0 0 1 1 *",
            "timeZone": "Europe/Helsinki",
            "overlapPolicy": "skip",
            "catchupWindowSeconds": 60,
            "paused": True,
        },
        "POST",
    )
    trigger = "compose-trigger-" + suffix
    check.request(f"/api/schedules/{schedule['id']}/trigger", {"triggerId": trigger}, "POST")
    check.request(f"/api/schedules/{schedule['id']}/trigger", {"triggerId": trigger}, "POST")
    until = time.monotonic() + 90
    scheduled = []
    while time.monotonic() < until:
        scheduled = [
            item
            for item in check.request("/api/runs")["items"]
            if item["origin"].get("scheduleId") == schedule["id"]
        ]
        if scheduled:
            break
        time.sleep(0.5)
    assert len(scheduled) == 1, "Repeated schedule trigger must create one logical Run"
    schedule_run = check.wait_run(scheduled[0]["id"])
    assert schedule_run["origin"]["kind"] == "schedule"
    check.request("/api/schedules/" + schedule["id"], method="DELETE")
    runs = [captured, model_run, report_run, schedule_run]
    return {
        "verifiedAt": datetime.now(UTC).isoformat(),
        "baseUrl": check.base,
        "financeUrl": check.finance,
        "runIds": [run["id"] for run in runs],
        "coreArtifacts": sorted({run["spec"]["coreArtifact"] for run in runs}),
        "artifactRefs": artifact_refs,
        "financeReportSlug": slug,
        "checks": [
            "HTTP authoring and launch",
            "launch deduplication",
            "Notes persistence",
            "content-addressed large values",
            "fake model evidence",
            "Finance Agent report provenance and immutability",
            "schedule trigger deduplication",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--finance-url", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--read-only", action="store_true")
    args = parser.parse_args()
    check = Check(args.base_url, args.finance_url)
    try:
        if args.read_only:
            evidence = json.loads(args.evidence.read_text())
            for run_id in evidence["runIds"]:
                assert check.request("/api/runs/" + run_id)["status"] == "succeeded"
            for ref in evidence["artifactRefs"]:
                check.artifact(ref)
            print("Historical runs and artifacts remain readable", flush=True)
        else:
            evidence = execute(check)
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(evidence, indent=2) + "\n")
            print(json.dumps(evidence), flush=True)
    finally:
        check.client.close()


if __name__ == "__main__":
    main()

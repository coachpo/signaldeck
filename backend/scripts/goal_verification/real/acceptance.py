"""Explicit acceptance phases. Uses real GLM only; never execute on import.

Run phases in order: configure, series, limits, faults. Offline checks are separate
because stopping owned services intentionally prevents subsequent workflow launches.
"""

import argparse
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from probe import OUT, configure, launch, record, request, wait_run

QUERY = "三项闭环预算候选"
PARAMS = {
    "title": QUERY + "整理",
    "query": QUERY,
    "summarize": True,
    "includeDerived": False,
    "text": (
        "请用中文整理查到的原始笔记，用笔记ID归属每个预算候选。"
        "必须保留10欧元、12欧元之间的矛盾以及尚未决策，不能自行选定最终预算；"
        "如有后续新原始资料也应归属来源保留。简洁输出约200汉字。"
        "使用Markdown，必须包含一个编号列表（1. 开头）和一个无序列表（- 开头），"
        "分别列候选与未决事项。"
    ),
}


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def select_parameter(parameter):
    return request(
        "/resources",
        {
            "resourceId": "research-model",
            "kind": "model",
            "config": {
                "name": "真实GLM三项闭环",
                "baseUrl": "http://127.0.0.1:4374/provider/v1",
                "modelId": "glm-5.3-flash",
                "apiStyle": "chat_completions",
                "timeoutSeconds": 180,
                "providerCapabilities": {"outputTokenLimitParameter": parameter},
            },
        },
    )


def configure_phase():
    configure(
        {"providerCapabilities": {"outputTokenLimitParameter": "max_tokens"}, "timeoutSeconds": 180}
    )
    package = request("/workflow-packages/research_notes")
    # Preserve the imported built-in definition and its immutable revision.
    save("package-baseline.json", package)


def require_success(row):
    assert row["status"] == "succeeded", (
        row["label"],
        row["id"],
        row["status"],
        row.get("errorCode"),
    )
    if row["packageKey"] == "research_notes":
        baseline = json.loads((OUT / "package-baseline.json").read_text())
        assert row["packageHash"] == baseline["packageHash"], "Built-in package revision changed"
    return row


def source_ids(row):
    tools = [
        e
        for e in row["evidence"]
        if e["kind"] == "tool"
        and e.get("toolId") == "example/notes/search"
        and e.get("status") == "succeeded"
    ]
    assert len(tools) == 1, (row["id"], "Expected one real search", tools)
    output = tools[0]["output"]
    if isinstance(output, dict) and "output" in output and "sourceNoteIds" not in output:
        output = output["output"]
    ids = output["sourceNoteIds"]
    assert set(ids) == {n["id"] for n in output["notes"]}
    assert all(n["sourceKind"] != "derived" for n in output["notes"])
    return sorted(ids)


def natural_schedule():
    now = datetime.now(ZoneInfo("Europe/Helsinki"))
    target = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    if (target - now).total_seconds() < 45:
        target += timedelta(minutes=1)
    body = {
        "name": "三项闭环自然定时",
        "packageKey": "research_notes",
        "workflowKey": "research",
        "parameters": PARAMS,
        "cron": f"{target.minute} {target.hour} {target.day} {target.month} *",
        "timeZone": "Europe/Helsinki",
        "paused": False,
        "overlapPolicy": "skip",
        "catchupWindowSeconds": 60,
    }
    schedule = request("/schedules", {**body, "requestId": str(uuid.uuid4())})
    print(
        json.dumps({"scheduleId": schedule["id"], "naturalFireAt": target.isoformat()}), flush=True
    )
    fires = []
    try:
        subprocess.run(
            [
                "node",
                str(
                    Path(os.environ["GOAL_WORKSPACE"])
                    / "frontend/scripts/goal-verification-schedule.mjs"
                ),
                "--base-url",
                "http://127.0.0.1:4374",
                "--schedule-id",
                schedule["id"],
                "--output",
                str(OUT),
                "--fire-at",
                target.isoformat(),
            ],
            check=True,
            timeout=40,
        )
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            fires = request("/schedules/" + schedule["id"] + "/fires")["items"]
            if fires and fires[0].get("runId"):
                break
            time.sleep(1)
    finally:
        schedule = request("/schedules/" + schedule["id"], {**body, "paused": True}, method="PATCH")
        save("schedule.json", {"schedule": schedule, "fires": fires})
    assert fires and fires[0].get("runId"), "Natural schedule did not launch; paused owned schedule"
    closed = json.loads((OUT / "schedule-browser.json").read_text())
    assert closed["browserClosed"] and closed["savedScheduleObserved"]
    assert datetime.fromisoformat(
        closed["closedAt"].replace("Z", "+00:00")
    ) < datetime.fromisoformat(fires[0]["scheduledAt"].replace("Z", "+00:00"))
    row = record(wait_run(fires[0]["runId"]), "series-natural-schedule")
    fires = request("/schedules/" + schedule["id"] + "/fires")["items"]
    save("schedule.json", {"schedule": schedule, "fires": fires})
    return row


def series_phase(originals=None, manual_label="series-manual"):
    if originals is None:
        originals = []
        for suffix, text in [
            ("A", "记录A：10欧元仅为预算候选，尚未批准。"),
            ("B", "记录B：12欧元是同一主题的另一个预算候选，与A不同，尚未决策。"),
        ]:
            row = require_success(
                launch(
                    "research_notes",
                    "capture",
                    {"title": QUERY + suffix, "text": text},
                    "original-" + suffix.lower(),
                )
            )
            originals.append(row["output"]["id"])
    manual = require_success(launch("research_notes", "research", PARAMS, manual_label))
    prepared = request(
        "/workflow-packages/research_notes/prepare",
        {
            "workflowKey": "research",
            "parameters": PARAMS,
            "revisionHash": manual["packageHash"],
            "sourceRunId": manual["id"],
        },
    )
    assert prepared["ready"], prepared["issues"]
    rerun = request(
        "/runs/" + manual["id"] + "/rerun",
        {"launchId": str(uuid.uuid4()), "bindingToken": prepared["bindingToken"]},
    )
    rerun = require_success(record(wait_run(rerun["id"]), "series-rerun"))
    scheduled = require_success(natural_schedule())
    first_three = [manual, rerun, scheduled]
    matrix = [
        {
            "label": r["label"],
            "runId": r["id"],
            "sourceNoteIds": source_ids(r),
            "savedNoteId": r["output"]["id"],
            "savedSourceNoteIds": r["output"]["sourceNoteIds"],
        }
        for r in first_three
    ]
    save(
        "source-sets.json",
        {
            "originalNoteIds": originals,
            "expectedOriginalNoteIds": originals,
            "collection": "observed-gaps",
            "runs": matrix,
        },
    )
    for row in first_three:
        assert source_ids(row) == sorted(originals), row["id"]
        assert sorted(row["output"]["sourceNoteIds"]) == sorted(originals), row["id"]
        assert row["output"]["sourceKind"] == "derived"
    fresh = require_success(
        launch(
            "research_notes",
            "capture",
            {
                "title": QUERY + "C",
                "text": "新原始记录C：14欧元为第三份候选，仍未作最终决定；不撤销记录A与B。",
            },
            "original-c-fresh",
        )
    )
    originals.append(fresh["output"]["id"])
    fourth = require_success(launch("research_notes", "research", PARAMS, "series-fresh-original"))
    matrix.append(
        {
            "label": fourth["label"],
            "runId": fourth["id"],
            "sourceNoteIds": source_ids(fourth),
            "savedNoteId": fourth["output"]["id"],
            "savedSourceNoteIds": fourth["output"]["sourceNoteIds"],
        }
    )
    save(
        "source-sets.json",
        {
            "originalNoteIds": originals,
            "expectedOriginalNoteIds": originals,
            "collection": "observed-gaps",
            "runs": matrix,
        },
    )
    assert source_ids(fourth) == sorted(originals)
    assert sorted(fourth["output"]["sourceNoteIds"]) == sorted(originals)
    included = require_success(
        launch(
            "research_notes",
            "research",
            {**PARAMS, "summarize": False, "includeDerived": True},
            "series-include-derived",
        )
    )
    searches = [
        e
        for e in included["evidence"]
        if e["kind"] == "tool" and e["toolId"] == "example/notes/search"
    ]
    assert len(searches) == 1
    result = searches[0]["output"]
    if "output" in result and "notes" not in result:
        result = result["output"]
    assert any(note["sourceKind"] == "derived" for note in result["notes"])
    assert set(originals) <= set(result["sourceNoteIds"])
    save(
        "include-derived.json",
        {
            "runId": included["id"],
            "search": result,
            "assertions": {"explicitFilterIncludesDerived": True, "originalsRemainIncluded": True},
        },
    )


def limit_package(key, cap):
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "unevaluatedProperties": False,
    }
    inputs = {"type": "object", "properties": {}, "required": [], "unevaluatedProperties": False}
    agent = {
        "name": "真实输出协议边界",
        "inputSchema": inputs,
        "outputSchema": schema,
        "strategy": {
            "kind": "model",
            "modelRef": "research-model",
            "prompt": (
                "请用JSON的text字段，中文详细说明预算候选10欧元和12欧元之间没有最终决定。"
                "至少100汉字，保留矛盾，不使用Markdown。"
            ),
        },
        "tools": [],
        "resources": [],
        "budget": {
            "maxModelRequests": 2,
            "maxToolCalls": 1,
            "maxTokens": 12000,
            "maxOutputTokens": cap,
            "deadlineSeconds": 420,
            "maxParallelTools": 1,
        },
    }
    workflow = {
        "name": "真实输出协议边界",
        "inputSchema": inputs,
        "outputSchema": schema,
        "nodes": {"work": {"uses": "writer", "inputMapping": {"ref": "workflow.input"}}},
        "outputMapping": {"ref": "nodes.work.output"},
        "maxParallelNodes": 1,
        "deadlineSeconds": 600,
        "presentation": {
            "version": "signaldeck.presentation/1",
            "title": {"kind": "static", "text": "真实输出协议边界"},
            "sections": [
                {
                    "kind": "markdown",
                    "ref": "workflow.output.text",
                    "label": "正文",
                    "required": True,
                }
            ],
        },
    }
    package = {
        "apiVersion": "signaldeck.workflowPackage/v2",
        "metadata": {"key": key, "name": "真实输出协议边界"},
        "agents": {"writer": agent},
        "workflows": {"run": workflow},
    }
    return request(
        "/workflow-packages", {"manifestSource": json.dumps(package, ensure_ascii=False)}
    )


def limits_phase():
    select_parameter("max_tokens")
    limit_package("gaps_limit_low", 16)
    low = launch("gaps_limit_low", "run", {}, "limit-effective-16")
    assert (
        low["status"] != "succeeded"
    ), "A truncated 16-token structured response cannot prove successful output"
    limit_package("gaps_limit_normal", 4096)
    normal = require_success(launch("gaps_limit_normal", "run", {}, "limit-normal-4096"))
    normal_events = normal["providerObservations"]
    assert normal_events and all(e["httpStatus"] == 200 for e in normal_events)
    assert all(e.get("maxTokens") == 4096 for e in normal_events)
    assert all(
        isinstance((e.get("usage") or {}).get("completion_tokens"), int)
        and 16 < e["usage"]["completion_tokens"] <= 4096
        for e in normal_events
    ), "Normal-cap success requires actual reported output usage"
    select_parameter("max_completion_tokens")
    try:
        limit_package("gaps_limit_violated", 16)
        violation = launch("gaps_limit_violated", "run", {}, "limit-provider-noncompliance-16")
    finally:
        select_parameter("max_tokens")
    projections = {
        r["label"]: request("/runs/" + r["id"] + "/result") for r in (low, normal, violation)
    }
    save(
        "limits.json",
        {"low": low, "normal": normal, "noncompliant": violation, "resultProjections": projections},
    )
    # Verify the reported over-cap response from relay, rather than assuming the
    # provider still ignores this field. Deterministic guard cases cover enforcement.
    effective = [e for e in low["providerObservations"] if e.get("maxTokens") == 16]
    assert effective and all(e.get("maxCompletionTokens") is None for e in effective)
    assert all(
        (e.get("usage") or {}).get("completion_tokens") is not None
        and e["usage"]["completion_tokens"] <= 16
        for e in effective
    ), "Missing or over-cap usage is not success proof"
    assert any(
        "length" in e.get("finishReasons", []) for e in effective
    ), "Low-cap actual finish reason was not length"
    noncompliant = [
        e
        for e in violation["providerObservations"]
        if e.get("maxCompletionTokens") == 16
        and (e.get("usage") or {}).get("completion_tokens", 0) > 16
    ]
    if not noncompliant:
        save(
            "noncompliance-observation.json",
            {
                "reproduced": False,
                "runId": violation["id"],
                "observations": violation["providerObservations"],
            },
        )
        return
    assert violation["status"] != "succeeded", "Over-cap response was incorrectly accepted"
    assert any(
        e.get("errorCode") == "model_output_limit_exceeded" for e in violation["evidence"]
    ), "No explicit output-limit violation evidence"
    assert any(
        e.get("errorCode") == "model_output_limit_exceeded"
        and (e.get("metadata") or {}).get("errorCategory") == "output_limit"
        for e in violation["evidence"]
    ), "Model evidence hides the output-limit diagnosis"
    assert (
        projections[violation["label"]]["errorCategory"] == "output_limit"
    ), "Result aggregate hides the output-limit diagnosis"
    assert (
        len([e for e in violation["evidence"] if e["kind"] == "model"]) == 1
    ), "Agent made more model calls after violation"
    assert len(violation["providerObservations"]) == 1, "Provider was invoked again after violation"
    assert (
        len(
            [
                e
                for e in violation["evidence"]
                if e["kind"] == "attempt"
                and (e.get("metadata") or {}).get("networkKind") == "model_request"
            ]
        )
        == 1
    )
    assert (
        violation["usageProjection"]["summary"]["outputTokens"]
        == noncompliant[0]["usage"]["completion_tokens"]
    ), "Already consumed output usage was not retained"


def faults_phase():
    try:
        save("notes-fault.json", {"mode": "read_error"})
        read = launch(
            "research_notes", "research", {**PARAMS, "summarize": False}, "read-unknown-fault"
        )
        save("notes-fault.json", {"mode": "write_reply_lost_recoverable"})
        recovered = require_success(
            launch(
                "research_notes",
                "capture",
                {
                    "title": "真实回复丢失但回执恢复",
                    "text": "自有故障验证：真实已提交，查询回执可用，允许恢复成功。",
                },
                "write-reply-lost-recovered-from-journal",
            )
        )
        save("notes-fault.json", {"mode": "write_reply_lost"})
        write = launch(
            "research_notes",
            "capture",
            {
                "title": "真实已提交但回复丢失",
                "text": "自有故障验证：实际写入已完成，不能无核实重复。",
            },
            "write-unknown-fault",
        )
    finally:
        save("notes-fault.json", {"mode": "off"})
    evidence = {}
    for label, row in [("read", read), ("recoveredWrite", recovered), ("write", write)]:
        evidence[label] = {
            "run": request("/runs/" + row["id"]),
            "result": request("/runs/" + row["id"] + "/result"),
        }
    writes = [
        e
        for e in write["evidence"]
        if e["kind"] == "tool" and e.get("toolId") == "example/notes/create"
    ]
    assert len(writes) == 1
    operation_id = writes[0]["operationId"]
    evidence["committedNote"] = request(
        "http://127.0.0.1:21082/api/note?id=" + quote(operation_id, safe=""), absolute=True
    )
    assert evidence["committedNote"]["id"] == operation_id
    save("read-write-faults.json", evidence)
    assert read["status"] != "succeeded" and write["status"] != "succeeded"
    assert not evidence["read"]["run"]["hasUnknownEffects"]
    assert evidence["read"]["result"]["readUnknownEvidenceIds"]
    assert evidence["write"]["run"]["hasUnknownEffects"]
    assert evidence["write"]["result"]["unknownEvidenceIds"]
    assert not evidence["recoveredWrite"]["run"]["hasUnknownEffects"]
    events = [
        json.loads(line) for line in (OUT / "notes-observations.jsonl").read_text().splitlines()
    ]
    assert (
        len(
            [
                e
                for e in events
                if e.get("operationId") == operation_id
                and e.get("toolId") == "example/notes/create"
            ]
        )
        == 1
    )
    assert any(
        e.get("operationId") == operation_id
        and e.get("fault") == "injected_operation_query_unavailable_after_committed_write"
        for e in events
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["configure", "series", "limits", "faults"])
    args = parser.parse_args()
    globals()[args.phase + "_phase"]()

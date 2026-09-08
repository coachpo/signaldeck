"""Run against an independently managed, pinned local Hatchet engine."""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from probe import ROOT, Input, call, dag, durable_agent, hatchet

PROCESSES = []


def worker(role):
    log = (ROOT / f"{role}-{len(PROCESSES)}.log").open("w")
    p = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("probe.py")), role],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    PROCESSES.append(p)
    return p


def events(run):
    path = ROOT / "events.jsonl"
    return (
        [e for line in path.read_text().splitlines() if (e := json.loads(line))["run"] == run]
        if path.exists()
        else []
    )


async def until(predicate, timeout=90):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.2)


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "core-v1_plugin-v1").write_text("immutable fixture v1")
    worker("calls")
    parent = worker("durable")
    await asyncio.sleep(5)
    report = {
        "versions": {"engine": "0.105.16", "hatchet-sdk": "1.40.0", "pydantic-ai-slim": "2.40.0"},
        "scope": "candidate probe; not platform acceptance",
        "results": {},
    }
    stamp = str(time.time_ns())
    rid = stamp + "-dag"
    result = await asyncio.wait_for(dag.aio_run(Input(run=rid)), 90)
    ev = events(rid)
    at = {(e["branch"], e["event"]): e["time"] for e in ev}
    assert at["E", "node-start"] < at["C", "node-confirmed"]
    assert (
        at["B", "node-start"] < at["C", "node-confirmed"]
        and at["C", "node-start"] < at["B", "node-confirmed"]
    )
    report["results"]["parallel-ready-dag"] = {"passed": True, "run": rid, "result": result}
    try:
        await asyncio.wait_for(dag.aio_run(Input(run=rid)), 15)
        duplicate = "unexpected second result"
    except Exception as exc:
        duplicate = type(exc).__name__
    assert len([e for e in events(rid) if e["branch"] == "A" and e["event"] == "node-start"]) == 1
    report["results"]["duplicate-delivery"] = {
        "passed": True,
        "result": duplicate,
        "limitation": "TTL dedup only; indefinite identity and transactional outbox untested",
    }
    runs = [
        Input(run=stamp + "-one", alias="plugin_one__lookup", value="one"),
        Input(run=stamp + "-two", alias="plugin_two__lookup", value="two"),
    ]
    values = await asyncio.wait_for(asyncio.gather(*(durable_agent.aio_run(i) for i in runs)), 90)
    assert [json.loads(v["result"])["value"] for v in values] == ["one", "two"]
    report["results"]["dynamic-schema-run-isolation"] = {
        "passed": True,
        "runs": [i.run for i in runs],
        "values": values,
    }
    spec = Input(run=stamp + "-recovery", pause=True)
    ref = await durable_agent.aio_run(spec, wait_for_result=False)
    await until(
        lambda: any(e["event"] == "model-start" and e.get("round") == 1 for e in events(spec.run))
    )
    os.killpg(parent.pid, signal.SIGKILL)
    parent.wait()
    worker("durable")
    await asyncio.sleep(3)
    (ROOT / (spec.run + "-release")).write_text("continue")
    recovered = await asyncio.wait_for(ref.aio_result(), 150)
    ev = events(spec.run)
    assert len([e for e in ev if e["event"] == "model-confirmed" and e["round"] == 0]) == 1
    assert len([e for e in ev if e["event"] == "tool-confirmed"]) == 1
    report["results"]["worker-kill-call-recovery"] = {
        "passed": True,
        "run": spec.run,
        "result": recovered,
        "kill": "SIGKILL durable worker group; call worker and engine remain alive",
    }
    fresh = await asyncio.wait_for(
        durable_agent.aio_run(spec.model_copy(update={"run": stamp + "-fresh", "pause": False})), 90
    )
    assert json.loads(fresh["result"])["fresh"] != json.loads(recovered["result"])["fresh"]
    report["results"]["new-run-freshness"] = {"passed": True}
    cancel_spec = Input(
        run=stamp + "-cancel", kind="tool", delay=30, schemas=[{"schema": {"type": "object"}}]
    )
    cancel_ref = await call.aio_run(cancel_spec, wait_for_result=False)
    await until(lambda: any(e["event"] == "tool-start" for e in events(cancel_spec.run)))
    await hatchet.runs.aio_cancel(cancel_ref.workflow_run_id)
    await until(
        lambda: any(e["event"] == "actual-cancelled" for e in events(cancel_spec.run)), timeout=30
    )
    assert not any(e["event"] == "tool-confirmed" for e in events(cancel_spec.run))
    report["results"]["active-call-cancellation"] = {
        "passed": True,
        "run": cancel_spec.run,
        "limitation": "direct task cancellation; parent propagation measured separately",
    }
    parent_cancel = Input(run=stamp + "-parent-cancel", pause=True)
    parent_ref = await durable_agent.aio_run(parent_cancel, wait_for_result=False)
    await until(
        lambda: any(
            e["event"] == "model-start" and e.get("round") == 1 for e in events(parent_cancel.run)
        )
    )
    await hatchet.runs.aio_cancel(parent_ref.workflow_run_id)
    try:
        await until(
            lambda: any(e["event"] == "actual-cancelled" for e in events(parent_cancel.run)),
            timeout=8,
        )
        propagated = True
    except TimeoutError:
        propagated = False
        (ROOT / (parent_cancel.run + "-release")).write_text("cleanup child")
    report["results"]["parent-child-cancellation"] = {
        "passed": propagated,
        "run": parent_cancel.run,
        "observation_seconds": 8,
    }
    for case, spec in [
        ("fixed-artifact-missing", Input(run=stamp + "-missing", artifact="absent")),
        ("total-deadline", Input(run=stamp + "-deadline", deadline=time.time() - 1)),
    ]:
        try:
            await asyncio.wait_for(call.aio_run(spec), 90)
            raise AssertionError("failure expected")
        except Exception as exc:
            assert type(exc).__name__ == "FailedTaskRunExceptionGroup"
            assert any(e["event"] == "boundary-rejected" for e in events(spec.run))
            report["results"][case] = {
                "passed": True,
                "error_type": type(exc).__name__,
                "limitation": "guard only; artifact routing and total deadline untested",
            }
    report["unverified"] = [
        "platform PostgreSQL atomic outbox",
        "indefinite Run identity beyond idempotency TTL",
        "deadline across retries and queue waiting",
        "real artifact loader and worker version routing",
        "MCP transport",
        "unknown external write reconciliation",
        "scheduling timezone overlap misfire",
    ]
    (ROOT / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        for p in PROCESSES:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
        for p in PROCESSES:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)

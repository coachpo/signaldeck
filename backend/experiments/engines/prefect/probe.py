"""Isolated real-server experiment; does not exercise SignalDeck APIs."""

import asyncio
import hashlib
import importlib.machinery
import importlib.metadata
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

from prefect.client.orchestration import get_client
from prefect.flow_engine import run_flow
from prefect.states import Scheduled
from workloads import ROOT, agent_flow, cancel_flow, dag_flow, deadline_flow

PROCESSES = []


def events():
    path = ROOT / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def spec(identity, value="fresh", crash=False):
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    pins = {}
    for role in ("core", "plugin"):
        payload = (
            Path(__file__).with_name("workloads.py").read_bytes()
            if role == "core"
            else b"import json,sys\nx=json.load(sys.stdin)\n"
            b'print(json.dumps({"value": x["value"], "version": "v1"}))\n'
        )
        digest = hashlib.sha256(payload).hexdigest()
        (artifacts / digest).write_bytes(payload)
        pins[role] = digest
    return {
        "run": identity,
        "value": value,
        "tool": f"plugin_{value}__read",
        "crash": crash,
        **pins,
    }


def process(run_id):
    log = (ROOT / f"worker-{run_id}.log").open("a")
    child = subprocess.Popen(
        [sys.executable, __file__, "worker", str(run_id)], stdout=log, stderr=subprocess.STDOUT
    )
    PROCESSES.append(child)
    return child


async def wait_for(predicate, seconds=40):
    end = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() > end:
            raise TimeoutError("probe condition did not become true")
        await asyncio.sleep(0.1)


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    report = {
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("prefect", "pydantic-ai-slim", "pydantic")
        },
        "python": sys.version,
        "checks": {},
    }
    checks = report["checks"]
    async with get_client() as client:
        run_spec = spec("recovery", crash=True)
        fr = await client.create_flow_run(
            agent_flow, parameters={"spec": run_spec}, state=Scheduled()
        )
        worker = process(fr.id)
        await wait_for(lambda: (ROOT / "confirmed").exists())
        await wait_for(
            lambda: any(x["kind"] == "node_end" and x.get("run") == "recovery" for x in events())
        )
        worker.kill()
        worker.wait(timeout=10)
        # Publish new current artifacts while this run retains its original content digests.
        for role in ("core", "plugin"):
            old = (ROOT / "artifacts" / run_spec[role]).read_bytes()
            changed = old + b"\n# newly published artifact v2\n"
            new_digest = hashlib.sha256(changed).hexdigest()
            (ROOT / "artifacts" / new_digest).write_bytes(changed)
            (ROOT / f"current-{role}").write_text(new_digest)
        checks["hard_kill"] = {"exit": worker.returncode, "flowRunId": str(fr.id)}
        before = [x for x in events() if x.get("run") == "recovery"]
        # Crash cache alone does not restart a worker. Explicitly resubmit the same engine identity.
        await client.set_flow_run_state(fr.id, Scheduled(), force=True)
        (ROOT / "release").write_text("resume")
        resumed = process(fr.id)
        await asyncio.to_thread(resumed.wait, 60)
        assert resumed.returncode == 0
        after = [x for x in events() if x.get("run") == "recovery"]
        assert len([x for x in after if x["kind"] == "tool"]) == 2
        assert {x["operation"] for x in after if x["kind"] == "tool"} == {
            "operation-1",
            "operation-2",
        }
        assert len([x for x in after if x["kind"] == "model" and x["round"] == 0]) == 1
        assert len([x for x in after if x["kind"] == "model" and x["round"] == 1]) == 2
        assert len([x for x in after if x["kind"] == "node_end"]) == 1
        checks["call_level_recovery"] = {
            "passed": True,
            "sameFlowRunId": str(fr.id),
            "firstEvents": before,
            "allEvents": after,
            "resubmission": "manual Scheduled state + run_flow; automatic crash pickup NOT tested",
        }
        completed = next(x for x in after if x["kind"] == "agent_complete")
        assert json.loads(completed["output"])["version"] == "v1"
        checks["frozen_executable_recovery"] = {
            "passed": True,
            "core": run_spec["core"],
            "plugin": run_spec["plugin"],
            "note": "platform loader uses frozen core/plugin source; image routing NOT tested",
        }
        checks["dynamic_and_isolation"] = {"passed": False}
        outputs = await asyncio.gather(
            agent_flow(spec("parallel-one", "one")), agent_flow(spec("parallel-two", "two"))
        )
        assert json.loads(outputs[0])["value"] == "one"
        assert json.loads(outputs[1])["value"] == "two"
        checks["dynamic_and_isolation"] = {
            "passed": True,
            "outputs": outputs,
            "note": "DynamicToolset enum schema and qualified alias asserted in actual model calls",
        }
        await agent_flow(spec("new-run", "fresh"))
        await agent_flow(spec("new-run", "fresh"))
        assert len([x for x in events() if x["kind"] == "tool" and x.get("run") == "new-run"]) == 4
        checks["new_run_freshness"] = {"passed": True}
        await dag_flow("dag")
        timeline = {
            f"{x['node']}_{x['kind']}": x["time"] for x in events() if x.get("run") == "dag"
        }
        assert timeline["B_node_start"] < timeline["C_node_end"]
        assert timeline["C_node_start"] < timeline["B_node_end"]
        assert timeline["E_node_end"] < timeline["C_node_end"]
        assert timeline["D_node_start"] >= timeline["C_node_end"]
        checks["parallel_ready_dag"] = {"passed": True, "timeline": timeline}
        pinned = spec("missing-artifact")
        (ROOT / "artifacts" / pinned["plugin"]).unlink()
        try:
            await agent_flow(pinned)
        except RuntimeError as exc:
            checks["missing_artifact"] = {
                "passed": "Missing frozen plugin" in str(exc),
                "note": "platform guard before replay; no native artifact routing tested",
            }
        else:
            raise AssertionError("missing artifact accepted")
        assert not [x for x in events() if x.get("run") == "missing-artifact"]
        cancellation = asyncio.create_task(cancel_flow())
        await wait_for(lambda: any(x["kind"] == "cancel_started" for x in events()))
        cancellation.cancel()
        try:
            await cancellation
        except asyncio.CancelledError:
            pass
        assert any(x["kind"] == "cancel_propagated" for x in events())
        assert not any(x["kind"] == "forbidden_downstream" for x in events())
        checks["cancel_local_propagation"] = {
            "passed": True,
            "note": "local cancellation; process cancellation covered in cancel_probe.py",
        }
        started = time.time()
        try:
            await deadline_flow(started + 0.4)
        except TimeoutError:
            pass
        deadline_events = [x for x in events() if x["kind"] == "deadline_attempt"]
        assert len(deadline_events) == 3
        assert deadline_events[1]["remaining"] <= 0 and deadline_events[2]["remaining"] <= 0
        checks["total_deadline"] = {
            "passed": True,
            "attempts": deadline_events,
            "note": "absolute deadline platform guard; retry native",
        }
        deployment = await agent_flow.to_deployment(name="idempotency", work_pool_name=None)
        deployment_id = await deployment.apply()
        command = {"spec": spec("outbox-command")}
        command_key = f"outbox-{ROOT.name}"
        first = await client.create_flow_run_from_deployment(
            deployment_id, parameters=command, idempotency_key=command_key
        )
        second = await client.create_flow_run_from_deployment(
            deployment_id, parameters=command, idempotency_key=command_key
        )
        assert first.id == second.id
        checks["duplicate_start_delivery"] = {
            "passed": True,
            "flowRunId": str(first.id),
            "note": "native idempotency key; SignalDeck atomic outbox transaction NOT tested",
        }
    report["not_tested"] = [
        "automatic crashed worker recovery",
        "MCP Streamable HTTP transport",
        "unknown external write resolution",
        "SignalDeck outbox transaction",
        "complete container/dependency artifact retention and routing",
    ]
    (ROOT / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


async def worker_main(identity):
    async with get_client() as client:
        fr = await client.read_flow_run(UUID(identity))
        digest = fr.parameters["spec"]["core"]
        path = ROOT / "artifacts" / digest
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Missing frozen core artifact: {digest}")
        loader = importlib.machinery.SourceFileLoader("frozen_workloads", str(path))
        module_spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[loader.name] = module
        loader.exec_module(module)
        await run_flow(module.agent_flow, flow_run=fr)


if __name__ == "__main__":
    try:
        asyncio.run(worker_main(sys.argv[2]) if len(sys.argv) > 1 else main())
    finally:
        for child in PROCESSES:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)

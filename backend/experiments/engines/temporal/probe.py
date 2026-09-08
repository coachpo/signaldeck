"""Run isolated real-server integration assertions, preserving JSON evidence."""

import asyncio
import hashlib
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.client import Client, WorkflowFailureError
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

HERE = Path(__file__).resolve().parent
QUEUE = "sd-target-temporal-probe"


async def wait_for(test, timeout=35):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if result := test():
            return result
        await asyncio.sleep(0.1)
    raise TimeoutError("probe condition did not become true")


async def main():
    with socket.socket() as port_check:
        port_check.bind(("127.0.0.1", 17233))
    root = Path(tempfile.mkdtemp(prefix="sd-temporal-probe-"))
    log = root / "events.jsonl"
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir()

    def artifact(content):
        identity = hashlib.sha256(content).hexdigest()
        (artifact_dir / identity).write_bytes(content)
        return identity

    core = artifact(b"core-v1")
    plugin = artifact(b"plugin-v1")
    plugin2 = artifact(b"plugin-v2")
    env = dict(
        os.environ,
        PROBE_LOG=str(log),
        PROBE_ARTIFACTS=str(artifact_dir),
        PROBE_ADDRESS="127.0.0.1:17233",
    )
    cli = os.environ.get("TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal")
    server_log = (root / "server.log").open("w")
    worker_log = (root / "worker.log").open("w")
    server = subprocess.Popen(
        [
            cli,
            "server",
            "start-dev",
            "--ip",
            "127.0.0.1",
            "--port",
            "17233",
            "--headless",
            "--db-filename",
            str(root / "temporal.db"),
        ],
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )
    worker = None
    evidence = {
        "root": str(root),
        "versions": {
            p: importlib.metadata.version(p)
            for p in ["temporalio", "pydantic-ai-slim", "jsonschema"]
        },
        "cli": subprocess.check_output([cli, "--version"], text=True).strip(),
        "checks": {},
    }

    def events():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def match(event, run):
        return [e for e in events() if e["event"] == event and e.get("run") == run]

    def start_worker():
        return subprocess.Popen(
            [sys.executable, str(HERE / "worker.py")],
            env=env,
            stdout=worker_log,
            stderr=subprocess.STDOUT,
        )

    def spec(run, value=3, pause=False, pin=plugin):
        schema = {
            "type": "object",
            "properties": {"value": {"type": "integer", "minimum": value}},
            "required": ["value"],
        }
        return dict(
            run=run,
            value=value,
            pause=pause,
            core=core,
            tools=[
                {
                    "id": f"acme/{owner}/search",
                    "alias": f"search_{owner}",
                    "artifact": pin,
                    "schema": schema,
                }
                for owner in ["one", "two"]
            ],
            grants=["acme/one/search", "acme/two/search"],
        )

    async def start(kind, data, timeout=60):
        return await client.start_workflow(
            kind,
            data,
            id=data["run"],
            task_queue=QUEUE,
            execution_timeout=timedelta(seconds=timeout),
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )

    try:
        for _ in range(100):
            try:
                client = await Client.connect(env["PROBE_ADDRESS"], plugins=[PydanticAIPlugin()])
                break
            except Exception:
                if server.poll() is not None:
                    raise RuntimeError("dev server exited") from None
                await asyncio.sleep(0.1)
        else:
            raise RuntimeError("dev server did not start")
        worker = start_worker()
        r = "recovery-" + uuid.uuid4().hex
        data = spec(r, pause=True)
        handle = await start("RecoveryWorkflow", data)
        await wait_for(
            lambda: any(e["step"] == 1 for e in match("model", r)) and match("node-end", r)
        )
        history = await handle.fetch_history()
        (root / "history-before-kill.json").write_text(history.to_json())
        worker.kill()
        worker.wait()
        artifact(b"plugin-new-release")
        (artifact_dir / "release").touch()
        worker = start_worker()
        output = json.loads(await asyncio.wait_for(handle.result(), 40))
        assert len(match("tool", r)) == 2
        assert len(match("node-start", r)) == 1
        evidence["checks"]["successfulSiblingRecovery"] = {"passed": True}
        assert len([e for e in match("model", r) if e["step"] == 0]) == 1
        assert all(v["artifact"] == plugin and v["run"] == r for v in output)
        evidence["checks"]["callRecovery"] = {
            "passed": True,
            "tools": match("tool", r),
            "modelSteps": [e["step"] for e in match("model", r)],
            "hardKill": "SIGKILL",
        }
        evidence["checks"]["frozenPluginRecovery"] = {
            "passed": True,
            "artifact": plugin,
            "scope": "digest-resolved fake artifact; same core worker restarted",
        }
        try:
            await start("AgentWorkflow", data)
            raise AssertionError("duplicate start accepted")
        except WorkflowAlreadyStartedError:
            evidence["checks"]["duplicateDelivery"] = {
                "passed": True,
                "scope": "engine workflow-id rejection, not PostgreSQL outbox atomicity",
            }
        one, two = spec("isolation-one-" + uuid.uuid4().hex, 13), spec(
            "isolation-two-" + uuid.uuid4().hex, 29, pin=plugin2
        )
        handles = await asyncio.gather(start("AgentWorkflow", one), start("AgentWorkflow", two))
        for d, h in zip([one, two], handles, strict=True):
            values = json.loads(await h.result())
            assert all(v["run"] == d["run"] and v["value"] == d["value"] for v in values)
            assert len(match("tool", d["run"])) == 2
            assert all(
                e["schemas"][0]["properties"]["value"]["minimum"] == d["value"]
                for e in match("model", d["run"])
            )
        evidence["checks"]["dynamicSchemaIsolationFreshness"] = {
            "passed": True,
            "runs": [one["run"], two["run"]],
        }
        bad = spec("missing-" + uuid.uuid4().hex, pin="f" * 64)
        missing = await start("AgentWorkflow", bad)
        try:
            await missing.result()
            raise AssertionError("missing artifact succeeded")
        except WorkflowFailureError as exc:
            cause = exc
            messages = []
            while cause is not None:
                messages.append(str(cause))
                cause = cause.__cause__
            assert any("frozen artifact unavailable" in msg for msg in messages), messages
            evidence["checks"]["missingArtifact"] = {"passed": True}
        for boundary in ["inputSchema", "grant", "coreArtifact"]:
            rejected = spec(boundary + "-" + uuid.uuid4().hex)
            if boundary == "inputSchema":
                rejected["value"] = -1
            elif boundary == "grant":
                rejected["grants"] = []
            else:
                rejected["core"] = "0" * 64
            h = await start("AgentWorkflow", rejected)
            try:
                await h.result()
                raise AssertionError(boundary + " succeeded")
            except WorkflowFailureError:
                assert not match("tool", rejected["run"])
                evidence["checks"][boundary + "Rejected"] = {"passed": True}
        graph_run = "graph-" + uuid.uuid4().hex
        graph = await start("GraphWorkflow", {"run": graph_run})
        await graph.result()
        stamps = {(e["event"], e["node"]): e["at"] for e in events() if e.get("run") == graph_run}
        assert stamps["node-start", "C"] < stamps["node-end", "B"]
        assert stamps["node-start", "E"] < stamps["node-end", "C"]
        assert stamps["node-start", "D"] > stamps["node-end", "C"]
        evidence["checks"]["parallelNodeReadiness"] = {
            "passed": True,
            "events": [e for e in events() if e.get("run") == graph_run],
        }
        for mode in ["cancel", "deadline"]:
            run = mode + "-" + uuid.uuid4().hex
            h = await start(
                "GraphWorkflow",
                {"run": run, "cancel": True},
                timeout=2 if mode == "deadline" else 60,
            )
            await wait_for(lambda run=run: match("node-start", run))
            if mode == "cancel":
                await h.cancel()
            try:
                await h.result()
                raise AssertionError(mode + " succeeded")
            except WorkflowFailureError:
                pass
            await wait_for(lambda run=run: match("node-cancelled", run), timeout=10)
            assert not any(e["node"] == "B" for e in match("node-start", run))
            evidence["checks"][mode] = {
                "passed": True,
                "events": [e for e in events() if e.get("run") == run],
            }
        (artifact_dir / "release").unlink()
        agent_cancel = spec("agent-cancel-" + uuid.uuid4().hex, pause=True)
        h = await start("AgentWorkflow", agent_cancel)
        await wait_for(lambda: any(e["step"] == 1 for e in match("model", agent_cancel["run"])))
        await h.cancel()
        try:
            await h.result()
            raise AssertionError("agent cancellation succeeded")
        except WorkflowFailureError:
            pass
        await wait_for(lambda: match("model-cancelled", agent_cancel["run"]))
        assert len(match("tool", agent_cancel["run"])) == 1
        evidence["checks"]["agentModelCancellation"] = {"passed": True}
        (root / "history-after-recovery.json").write_text((await handle.fetch_history()).to_json())
        evidence["unverified"] = [
            "PostgreSQL transactional outbox interruption",
            "cross-core-version worker routing",
            "MCP transport",
            "tool output schema rejection",
            "unknown side-effect reconciliation",
            "retries under total deadline",
            "Temporal schedules",
        ]
        evidence["result"] = "passed within recorded scope"
    finally:
        if worker is not None:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        evidence["processesStopped"] = True
        (root / "evidence.json").write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

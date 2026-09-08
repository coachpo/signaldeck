"""Verify real product recovery across independent Notes and Core releases locally.

Run: PYTHONPATH=backend backend/.venv/bin/python backend/scripts/verify_platform_recovery.py
Only UUID databases and child processes created by this script are cleaned up.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from platform_recovery_provider import RecoveryProvider
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.core_artifacts import CoreArtifactStore, task_queue
from app.infrastructure.temporal_client import connect_client
from app.workers.artifact_worker import prepare_environment

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
REPORTS = REPO / ".steward/goals/sd-target-001/verification/platform-recovery"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def call(api: str, method: str, path: str, data: Any = None) -> Any:
    response = httpx.request(method, api + path, json=data, timeout=30)
    if response.status_code >= 400:
        raise AssertionError(f"{method} {path}: {response.status_code}: {response.text[:1000]}")
    return response.json()


def ready(api: str, timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(api + "/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise TimeoutError("Local process did not become ready")


def wait_run(api: str, run_id: str, predicate, timeout: float = 180) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        detail = call(api, "GET", "/api/runs/" + run_id)
        if predicate(detail):
            return detail
        if detail["status"] in ("failed", "cancelled"):
            raise AssertionError("Product Run ended: " + json.dumps(detail)[:2000])
        time.sleep(0.2)
    raise TimeoutError("Product Run did not reach the required observable state")


def package(instructions: str) -> str:
    def obj(properties: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "properties": properties, "required": list(properties)}

    string = {"type": "string"}
    note = obj({key: string for key in ("id", "collection", "title", "text")})
    agent_output = obj({"note": note, "modelId": string, "instructions": string})
    title = {"type": "string", "minLength": 1, "maxLength": 200}
    create_input = obj({"title": title, "text": {"type": "string", "maxLength": 100000}})
    source = {
        "apiVersion": "signaldeck.workflowPackage/v2",
        "metadata": {"key": "recovery", "name": "Executable recovery verification"},
        "agents": {
            "writer": {
                "inputSchema": obj({"tag": string}),
                "outputSchema": agent_output,
                "strategy": {"kind": "model", "modelRef": "recovery-model", "prompt": instructions},
                "tools": ["example/notes/create", "example/notes/search"],
                "resources": ["notes-workspace"],
                "budget": {
                    "maxModelRequests": 5,
                    "maxToolCalls": 5,
                    "maxTokens": 200000,
                    "deadlineSeconds": 360,
                },
            },
            "sibling": {
                "inputSchema": create_input,
                "outputSchema": note,
                "strategy": {"kind": "deterministic", "toolId": "example/notes/create"},
                "tools": ["example/notes/create"],
                "resources": ["notes-workspace"],
            },
        },
        "workflows": {
            "main": {
                "inputSchema": obj({"tag": string, "siblingTitle": title}),
                "outputSchema": obj({"agent": agent_output, "sibling": note}),
                "nodes": {
                    "agent": {
                        "uses": "writer",
                        "inputMapping": {
                            "object": {
                                "tag": {"ref": "workflow.input.tag"},
                            }
                        },
                    },
                    "sibling": {
                        "uses": "sibling",
                        "inputMapping": {
                            "object": {
                                "title": {"ref": "workflow.input.siblingTitle"},
                                "text": {"value": "sibling"},
                            }
                        },
                    },
                },
                "outputMapping": {
                    "object": {
                        "agent": {"ref": "nodes.agent.output"},
                        "sibling": {"ref": "nodes.sibling.output"},
                    }
                },
                "deadlineSeconds": 420,
            }
        },
    }
    return json.dumps(source)


def worker_process(supervisor: int, digest: str, timeout: float = 60) -> dict[str, Any]:
    expected = digest.removeprefix("sha256:") + "/bin/python"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        output = subprocess.check_output(["ps", "-axo", "pid,ppid,command"], text=True)
        for line in output.splitlines()[1:]:
            values = line.strip().split(None, 2)
            if len(values) == 3 and int(values[1]) == supervisor and expected in values[2]:
                pid = int(values[0])
                if sys.platform == "darwin":
                    entries = subprocess.check_output(
                        ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                        text=True,
                    ).splitlines()
                    cwd = next(line[1:] for line in entries if line.startswith("n"))
                else:
                    cwd = os.readlink(f"/proc/{pid}/cwd")
                return {"pid": pid, "command": values[2], "cwd": cwd, "digest": digest}
        time.sleep(0.1)
    raise TimeoutError("A real artifact worker was not observed")


def collect_run(api: str, detail: dict[str, Any], report: Path) -> tuple[Any, list[str]]:
    write_json(report / "runs" / (detail["id"] + ".json"), detail)
    downloaded = set()

    def inflate(value: Any) -> Any:
        if isinstance(value, dict) and set(value) == {"$artifact"}:
            ref = value["$artifact"]
            response = httpx.get(api + "/api/artifacts/" + ref["digest"], timeout=30)
            assert response.status_code == 200
            assert "sha256:" + hashlib.sha256(response.content).hexdigest() == ref["digest"]
            assert len(response.content) == ref["sizeBytes"]
            target = report / "artifacts" / ref["digest"].removeprefix("sha256:")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)
            downloaded.add(ref["digest"])
            return inflate(response.json())
        if isinstance(value, dict):
            return {key: inflate(child) for key, child in value.items()}
        if isinstance(value, list):
            return [inflate(child) for child in value]
        return value

    output = inflate(detail["output"])
    for evidence in detail["evidence"]:
        inflate(evidence["input"])
        inflate(evidence["output"])
    by_id = {item["id"]: item for item in detail["evidence"]}
    for item in detail["evidence"]:
        if item["kind"] == "node":
            assert item["parentId"] is None
        else:
            assert item["parentId"] in by_id
            assert by_id[item["parentId"]]["nodeId"] == item["nodeId"]
    assert {item["kind"] for item in detail["evidence"]} == {
        "node",
        "agent",
        "model",
        "tool",
        "attempt",
    }
    assert downloaded
    return output, sorted(downloaded)


async def histories(
    address: str, artifacts: Path, runs: list[str], report: Path
) -> list[dict[str, Any]]:
    client = await connect_client(address, ArtifactStore(artifacts))
    summaries = []
    for run in runs:
        detail = json.loads((report / "runs" / (run + ".json")).read_text())
        expected_queue = task_queue(detail["spec"]["coreArtifact"])
        pending = [run]
        while pending:
            workflow_id = pending.pop()
            history = await client.get_workflow_handle(workflow_id).fetch_history()
            for event in history.events:
                wire = event.SerializeToString()
                assert all(f"recovery-model-credential-{n}".encode() not in wire for n in (1, 2))
            started = history.events[0].workflow_execution_started_event_attributes
            assert started.workflow_type.name == (
                "SignalDeckWorkflow" if workflow_id == run else "AgentWorkflow"
            )
            assert started.task_queue.name == expected_queue
            target = report / f"temporal-{workflow_id}.json"
            target.write_text(history.to_json())
            summaries.append(
                {
                    "workflowId": workflow_id,
                    "type": started.workflow_type.name,
                    "taskQueue": expected_queue,
                    "eventCount": len(history.events),
                    "historyFile": target.name,
                }
            )
            pending.extend(
                event.child_workflow_execution_started_event_attributes.workflow_execution.workflow_id
                for event in history.events
                if event.HasField("child_workflow_execution_started_event_attributes")
            )
    return summaries


def main() -> None:
    identity = uuid4().hex
    root = Path(tempfile.mkdtemp(prefix="signaldeck-platform-recovery-"))
    report = REPORTS / identity
    report.mkdir(parents=True)
    print(f"Evidence: {report}", flush=True)
    processes: list[subprocess.Popen] = []
    database_names = ["sd_recovery_" + identity, "sd_notes_" + identity]
    state: dict[str, Any] = {
        "status": "running",
        "targetBaseline": "bca05dcd666e96561426224b89b0e06aed186a22",
        "workDirectory": str(root),
        "databaseNames": database_names,
        "commands": [],
        "runs": {},
    }
    write_json(report / "report.json", state)
    admin = None
    provider = RecoveryProvider(report / "provider-events.jsonl")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("LOGFIRE_", "OTEL_"))
        and key not in {"PYTHONPATH", "VIRTUAL_ENV", "OPENAI_API_KEY", "SIGNALDECK_API_TOKEN"}
    }
    env.update(
        PYTHONDONTWRITEBYTECODE="1",
        LOGFIRE_SEND_TO_LOGFIRE="false",
        OTEL_SDK_DISABLED="true",
        SIGNALDECK_RUNTIME_MODE="test",
        AGENT_PLATFORM_ENCRYPTION_KEY="isolated-recovery-" + identity,
        SIGNALDECK_ARTIFACT_DIR=str(root / "artifacts"),
        SIGNALDECK_CORE_ARTIFACT_DIR=str(root / "core"),
        SIGNALDECK_CORE_ENV_DIR=str(root / "environments"),
    )

    def launch(name: str, command: list[str], cwd: Path, child_env: dict[str, str] = env):
        output = (report / (name + ".log")).open("w")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=child_env,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes.append(process)
        state["commands"].append(
            {"name": name, "command": command, "cwd": str(cwd), "pid": process.pid}
        )
        return process

    try:
        container = os.environ.get("RECOVERY_POSTGRES_CONTAINER", "signaldeck-target-test-postgres")
        mapping = subprocess.check_output(
            ["docker", "port", container, "5432/tcp"], text=True
        ).strip()
        host, postgres_port = mapping.splitlines()[0].rsplit(":", 1)
        assert host == "127.0.0.1", "Only the explicitly local PostgreSQL binding is allowed"
        configuration = json.loads(
            subprocess.check_output(["docker", "inspect", container], text=True)
        )[0]
        postgres_env = dict(
            item.split("=", 1) for item in configuration["Config"]["Env"] if "=" in item
        )
        admin_url = URL.create(
            "postgresql+psycopg",
            username=postgres_env.get("POSTGRES_USER", "postgres"),
            password=postgres_env.get("POSTGRES_PASSWORD"),
            host=host,
            port=int(postgres_port),
            database="postgres",
        )
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
        with admin.connect() as connection:
            for name in database_names:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
        env["DATABASE_URL"] = admin_url.set(database=database_names[0]).render_as_string(
            hide_password=False
        )
        notes_url = admin_url.set(database=database_names[1]).render_as_string(hide_password=False)
        state["postgres"] = {"container": container, "host": host, "port": int(postgres_port)}
        store = CoreArtifactStore(root / "core", BACKEND)
        old = store.publish()
        python = prepare_environment(old, root / "environments")
        state["installedDependencies"] = json.loads(
            subprocess.check_output(
                [
                    str(python),
                    "-I",
                    "-B",
                    "-c",
                    "import importlib.metadata as m,json; "
                    "print(json.dumps({n:m.version(n) for n in "
                    "['temporalio','pydantic-ai-slim','mcp','sqlalchemy','psycopg']}))",
                ],
                text=True,
            )
        )
        write_json(report / "core-v1-manifest.json", old.manifest)
        state["coreV1"] = {
            "digest": old.digest,
            "path": str(old.path),
            "python": old.python_version,
        }
        temporal_port = port()
        address = f"127.0.0.1:{temporal_port}"
        env["TEMPORAL_ADDRESS"] = address
        cli = os.environ.get("TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal")
        launch(
            "temporal",
            [
                cli,
                "server",
                "start-dev",
                "--ip",
                "127.0.0.1",
                "--port",
                str(temporal_port),
                "--headless",
                "--db-filename",
                str(root / "temporal.db"),
            ],
            root,
        )
        supervisor = launch(
            "supervisor",
            [str(python), "-B", "-m", "app.workers.artifact_worker", "--serve"],
            old.path,
        )
        launch("dispatcher", [str(python), "-B", "-m", "app.workers.command_dispatcher"], old.path)
        api1_port = port()
        api1 = f"http://127.0.0.1:{api1_port}"
        api1_process = launch(
            "api-v1",
            [
                str(python),
                "-B",
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api1_port),
                "--no-access-log",
            ],
            old.path,
        )
        ready(api1)

        def notes(release_number: int) -> dict[str, Any]:
            destination = root / f"notes-release-{release_number}"
            for name in ("notes", "runtime"):
                shutil.copytree(
                    REPO / "plugins" / name,
                    destination / name,
                    ignore=shutil.ignore_patterns(
                        ".venv", "__pycache__", "*.pyc", ".env", ".pytest_cache"
                    ),
                )
            project = destination / "notes"
            if release_number == 2:
                code = project / "notes_plugin/main.py"
                changed = code.read_text().replace(
                    '"text": arguments["text"],', '"text": "notes-v2-write::" + arguments["text"],'
                )
                changed = changed.replace('"text": n.text}', '"text": "notes-v2-read::" + n.text}')
                assert changed != code.read_text()
                code.write_text(changed)
                (project / "VERSION").write_text("2.0.0\n")
                pyproject = project / "pyproject.toml"
                pyproject.write_text(
                    pyproject.read_text().replace('version = "1.0.0"', 'version = "2.0.0"')
                )
                subprocess.run(
                    ["uv", "lock", "--python", "3.13.13", "--project", str(project)],
                    check=True,
                    capture_output=True,
                )
            plugin_env = dict(
                env,
                PLUGIN_DATABASE_URL=notes_url,
                PYTHONPATH=str(destination / "runtime") + os.pathsep + str(project),
                UV_PROJECT_ENVIRONMENT=str(root / f"notes-env-{release_number}"),
            )
            subprocess.run(
                [
                    "uv",
                    "sync",
                    "--locked",
                    "--no-dev",
                    "--python",
                    "3.13.13",
                    "--project",
                    str(project),
                ],
                env=plugin_env,
                check=True,
                capture_output=True,
            )
            plugin_port = port()
            plugin_env["PLUGIN_ENDPOINT"] = f"http://127.0.0.1:{plugin_port}/mcp/"
            launch(
                f"notes-v{release_number}",
                [
                    str(root / f"notes-env-{release_number}/bin/python"),
                    "-B",
                    "-m",
                    "uvicorn",
                    "notes_plugin.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(plugin_port),
                    "--no-access-log",
                ],
                project,
                plugin_env,
            )
            endpoint = f"http://127.0.0.1:{plugin_port}"
            ready(endpoint)
            descriptor = call(endpoint, "GET", "/release")
            write_json(report / f"notes-v{release_number}-release.json", descriptor)
            return descriptor

        first_release = notes(1)
        call(api1, "POST", "/api/plugins", {"release": first_release, "enabled": True})
        call(
            api1,
            "POST",
            "/api/resources",
            {
                "resourceId": "notes-workspace",
                "kind": "tool",
                "config": {"pluginId": "example/notes", "scope": {"collection": "recovery"}},
            },
        )

        def model(api: str, version: int) -> None:
            # An explicit credential write revokes old pending references. This
            # scenario changes only the non-sensitive profile after initial setup.
            call(
                api,
                "POST",
                "/api/resources",
                {
                    "resourceId": "recovery-model",
                    "kind": "model",
                    "config": {
                        "baseUrl": provider.url,
                        "modelId": f"fake-model-v{version}",
                        "timeoutSeconds": 240,
                    },
                    **(
                        {"credentials": {"apiKey": "recovery-model-credential-1"}}
                        if version == 1
                        else {}
                    ),
                },
            )

        model(api1, 1)
        original_source = package("definition-one")
        call(api1, "POST", "/api/workflow-packages", {"manifestSource": original_source})

        def run(api: str, tag: str) -> dict[str, Any]:
            summary = call(
                api,
                "POST",
                "/api/workflow-packages/recovery/launches",
                {
                    "workflowKey": "main",
                    "parameters": {"tag": tag, "siblingTitle": "sibling-" + tag},
                },
            )
            state["runs"][tag] = summary["id"]
            return summary

        retained = run(api1, "retained")

        def confirmed(detail):
            evidence = detail["evidence"]
            return (
                any(
                    e["nodeId"] == "sibling" and e["kind"] == "node" and e["status"] == "succeeded"
                    for e in evidence
                )
                and any(
                    e["nodeId"] == "agent" and e["kind"] == "tool" and e["status"] == "succeeded"
                    for e in evidence
                )
                and any(e["kind"] == "model" and e["status"] == "succeeded" for e in evidence)
                and provider.gated.is_set()
            )

        before = wait_run(api1, retained["id"], confirmed)
        write_json(report / "before-interruption.json", before)
        old_process = worker_process(supervisor.pid, old.digest)
        assert Path(old_process["cwd"]).resolve() == old.path.resolve()
        state["workerBeforeInterruption"] = old_process
        os.killpg(old_process["pid"], signal.SIGKILL)

        second_release = notes(2)
        assert second_release["artifactDigest"] != first_release["artifactDigest"]
        call(api1, "POST", "/api/plugins", {"release": second_release, "enabled": True})
        same_core = run(api1, "plugin-upgrade")
        same_detail = wait_run(api1, same_core["id"], lambda d: d["status"] == "succeeded")
        assert api1_process.poll() is None
        assert same_detail["spec"]["coreArtifact"] == old.digest
        assert (
            same_detail["spec"]["pluginReleases"][0]["artifactDigest"]
            == second_release["artifactDigest"]
        )
        same_output, _ = collect_run(api1, same_detail, report)
        assert same_output["agent"]["note"]["text"].startswith("notes-v2-read::notes-v2-write::")

        source2 = root / "core-v2-source"
        shutil.copytree(old.path, source2)
        (source2 / "VERSION").chmod(0o644)
        (source2 / "VERSION").write_text("0.1.0-recovery-core-two\n")
        new = CoreArtifactStore(root / "core", source2).publish()
        assert new.digest != old.digest
        write_json(report / "core-v2-manifest.json", new.manifest)
        python2 = prepare_environment(new, root / "environments")
        api2_port = port()
        api2 = f"http://127.0.0.1:{api2_port}"
        launch(
            "api-v2",
            [
                str(python2),
                "-B",
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api2_port),
                "--no-access-log",
            ],
            new.path,
        )
        ready(api2)
        model(api2, 2)
        call(
            api2,
            "PATCH",
            "/api/workflow-packages/recovery",
            {"manifestSource": package("definition-two")},
        )
        current = run(api2, "core-upgrade")
        current_detail = wait_run(api2, current["id"], lambda d: d["status"] == "succeeded")
        assert current_detail["spec"]["coreArtifact"] == new.digest
        assert current_detail["packageHash"] != before["packageHash"]
        current_output, _ = collect_run(api2, current_detail, report)
        assert current_output["agent"]["modelId"] == "fake-model-v2"
        assert current_output["agent"]["instructions"] == "definition-two"
        new_process = worker_process(supervisor.pid, new.digest)
        assert Path(new_process["cwd"]).resolve() == new.path.resolve()
        state["coreV2"] = {"digest": new.digest, "path": str(new.path), "worker": new_process}
        provider.release.set()
        after = wait_run(api1, retained["id"], lambda d: d["status"] == "succeeded")
        assert after["spec"] == before["spec"]
        old_output, refs = collect_run(api1, after, report)
        assert old_output["agent"]["modelId"] == "fake-model-v1"
        assert old_output["agent"]["instructions"] == "definition-one"
        assert old_output["agent"]["note"]["text"].startswith("body-retained:")
        assert old_output["sibling"]["text"] == "sibling"
        confirmed_before = {e["id"]: e for e in before["evidence"] if e["status"] == "succeeded"}
        confirmed_after = {e["id"]: e for e in after["evidence"]}
        for key, evidence in confirmed_before.items():
            assert confirmed_after[key] == evidence
        unknown = [
            e for e in after["evidence"] if e["kind"] == "attempt" and e["status"] == "unknown"
        ]
        assert any(e["errorCode"] == "worker_interrupted" for e in unknown)
        old_now = worker_process(supervisor.pid, old.digest)
        assert old_now["pid"] != old_process["pid"]
        assert Path(old_now["cwd"]).resolve() == old.path.resolve()
        state["workerAfterRecovery"] = old_now
        events = [json.loads(line) for line in provider.events.read_text().splitlines()]
        assert len([e for e in events if e["tag"] == "retained" and e["round"] == 0]) == 1
        assert len([e for e in events if e["tag"] == "retained" and e["round"] == 1]) >= 2
        assert {e["model"] for e in events if e["tag"] == "retained"} == {"fake-model-v1"}
        notes_engine = create_engine(notes_url, hide_parameters=True)
        with notes_engine.connect() as connection:
            operations = connection.execute(
                text("SELECT operation_id, tool_id FROM plugin_operations")
            ).all()
        notes_engine.dispose()
        retained_operations = [row[0] for row in operations if row[0].startswith(retained["id"])]
        assert len(retained_operations) == 2
        assert len(operations) == 6
        state["temporalExecutions"] = asyncio.run(
            histories(address, root / "artifacts", list(state["runs"].values()), report)
        )
        for path in [*(report.rglob("*.json")), *(root / "artifacts").rglob("*")]:
            if path.is_file():
                data = path.read_bytes()
                assert all(f"recovery-model-credential-{n}".encode() not in data for n in (1, 2))
        state.update(
            status="passed",
            oldConfirmedModelCalls=1,
            oldWriteEffects=2,
            unknownNetworkAttempts=len(unknown),
            retrievedArtifacts=refs,
            notesV1=first_release["artifactDigest"],
            notesV2=second_release["artifactDigest"],
            sourceSnapshotUnchanged=True,
            sameCorePluginUpgrade=True,
            fullProductWorkerRecovery=True,
            wireSecretAbsenceChecked=True,
            versions={
                "python": old.python_version,
                "uv": subprocess.check_output(["uv", "--version"], text=True).strip(),
                "temporal": subprocess.check_output([cli, "--version"], text=True).strip(),
            },
            unverified=[
                "Browser visual flow",
                "Schedule overlap/misfire",
                "All workers and engine simultaneous crash",
                "Database-role isolation (this fixture uses distinct UUID databases)",
            ],
        )
    except BaseException as exc:
        state.update(status="failed", errorType=type(exc).__name__, error=str(exc)[:3000])
        raise
    finally:
        provider.stop()
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        state["processExitCodes"] = {str(p.pid): p.returncode for p in processes}
        workers = [
            state.get("workerBeforeInterruption"),
            state.get("workerAfterRecovery"),
            state.get("coreV2", {}).get("worker"),
        ]
        remaining = []
        for worker in workers:
            if worker is not None:
                try:
                    os.kill(worker["pid"], 0)
                    remaining.append(worker["pid"])
                except ProcessLookupError:
                    pass
        state["ownedWorkersStopped"] = not remaining
        if admin is not None:
            with admin.connect() as connection:
                for name in database_names:
                    connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            admin.dispose()
        state["ownedDatabasesRemoved"] = admin is not None
        write_json(report / "report.json", state)
        print(
            json.dumps({"status": state["status"], "report": str(report / "report.json")}),
            flush=True,
        )


if __name__ == "__main__":
    main()

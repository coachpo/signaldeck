"""Exercise two executable core bundles against a real isolated Temporal server."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from temporalio.client import Client

from app.infrastructure.core_artifacts import CoreArtifactStore, task_queue

BACKEND = Path(__file__).resolve().parents[1]
WORKER = """import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker
from app.infrastructure.core_artifacts import CoreArtifactStore

VERSION = {version!r}

@activity.defn
async def implementation(round_number: int) -> str:
    with Path(os.environ["CORE_PROBE_EVENTS"]).open("a") as stream:
        stream.write(json.dumps({{"version": VERSION, "round": round_number, "pid": os.getpid(),
          "run": activity.info().workflow_id,
          "artifact": os.environ["SIGNALDECK_CORE_ARTIFACT"]}}) + "\\n")
    return VERSION

@workflow.defn(name="ArtifactRecovery")
class ArtifactRecovery:
    def __init__(self):
        self.ready = False
        self.results = []

    @workflow.run
    async def run(self) -> list[str]:
        self.results.append(await workflow.execute_activity(implementation, 1,
            start_to_close_timeout=timedelta(seconds=10)))
        await workflow.wait_condition(lambda: self.ready)
        self.results.append(await workflow.execute_activity(implementation, 2,
            start_to_close_timeout=timedelta(seconds=10)))
        return self.results

    @workflow.signal
    def proceed(self):
        self.ready = True

    @workflow.query
    def progress(self):
        return self.results

async def main():
    store = CoreArtifactStore(Path(os.environ["SIGNALDECK_CORE_ARTIFACT_DIR"]))
    store.verify_worker(os.environ["SIGNALDECK_CORE_ARTIFACT"])
    client = await Client.connect(os.environ["CORE_PROBE_ADDRESS"])
    async with Worker(client, task_queue=os.environ["SIGNALDECK_TASK_QUEUE"],
            workflows=[ArtifactRecovery], activities=[implementation]):
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
"""


async def wait_for_query(handle, expected: list[str]) -> None:
    async with asyncio.timeout(45):
        while True:
            try:
                if await handle.query("progress") == expected:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.1)


async def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="signaldeck-core-recovery-"))
    print(f"Evidence: {root}", flush=True)
    source = root / "source"
    for name in ["app", "app/workers", "app/infrastructure"]:
        (source / name).mkdir(parents=True, exist_ok=True)
        (source / name / "__init__.py").write_text("")
    for name in ["pyproject.toml", "uv.lock", "README.md", "VERSION"]:
        shutil.copyfile(BACKEND / name, source / name)
    shutil.copyfile(
        BACKEND / "app/infrastructure/core_artifacts.py",
        source / "app/infrastructure/core_artifacts.py",
    )
    implementation = source / "app/workers/durable_worker.py"
    implementation.write_text(WORKER.format(version="core-one"))
    store = CoreArtifactStore(root / "artifacts", source)
    old = store.publish()
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    address = f"127.0.0.1:{port}"
    log = (root / "server.log").open("w")
    server = subprocess.Popen(
        [
            os.environ.get("TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"),
            "server",
            "start-dev",
            "--ip",
            "127.0.0.1",
            "--port",
            str(port),
            "--headless",
            "--db-filename",
            str(root / "temporal.db"),
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    workers: list[subprocess.Popen] = []
    env = dict(
        os.environ,
        SIGNALDECK_CORE_ARTIFACT_DIR=str(store.root),
        SIGNALDECK_CORE_ENV_DIR=str(root / "environments"),
        CORE_PROBE_ADDRESS=address,
        CORE_PROBE_EVENTS=str(root / "events.jsonl"),
    )

    def start(digest: str | None = None) -> subprocess.Popen:
        worker_log = (root / f"worker-{len(workers)}.log").open("w")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "app.workers.artifact_worker",
                *(["--digest", digest] if digest else ["--serve"]),
            ],
            cwd=BACKEND,
            env=env,
            stdout=worker_log,
            stderr=subprocess.STDOUT,
        )
        workers.append(process)
        return process

    try:
        client = None
        for _ in range(100):
            try:
                client = await Client.connect(address)
                break
            except RuntimeError:
                await asyncio.sleep(0.1)
        assert client is not None
        supervisor = start()
        handle = await client.start_workflow(
            "ArtifactRecovery", id="retained-run", task_queue=task_queue(old.digest)
        )
        await wait_for_query(handle, ["core-one"])
        first = json.loads((root / "events.jsonl").read_text().splitlines()[0])
        os.killpg(first["pid"], signal.SIGKILL)
        implementation.write_text(WORKER.format(version="core-two"))
        new = store.publish()
        assert old.digest != new.digest
        # The current source and latest retained closure are now core-two, but the
        # same logical Run must continue with the executable bytes from core-one.
        newer = await client.start_workflow(
            "ArtifactRecovery", id="new-run", task_queue=task_queue(new.digest)
        )
        await wait_for_query(newer, ["core-two"])
        await handle.signal("proceed")
        await newer.signal("proceed")
        old_result, new_result = await asyncio.wait_for(
            asyncio.gather(handle.result(), newer.result()),
            45,
        )
        assert old_result == ["core-one", "core-one"]
        assert new_result == ["core-two", "core-two"]
        events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
        assert len([e for e in events if e["run"] == "retained-run" and e["round"] == 1]) == 1
        assert {e["artifact"] for e in events if e["run"] == "retained-run"} == {old.digest}
        missing = start("sha256:" + "0" * 64)
        assert await asyncio.to_thread(missing.wait, 10) == 2
        tampered_file = new.path / "app/workers/durable_worker.py"
        tampered_file.chmod(0o644)
        original = tampered_file.read_bytes()
        tampered_file.write_bytes(original + b"\n# tampered\n")
        tampered = start(new.digest)
        assert await asyncio.to_thread(tampered.wait, 10) == 2
        tampered_file.write_bytes(original)
        tampered_file.chmod(0o444)
        supervisor.terminate()
        assert await asyncio.to_thread(supervisor.wait, 15) == 0
        for pid in {event["pid"] for event in events}:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            raise AssertionError("Supervisor left an owned worker alive")
        report = {
            "oldDigest": old.digest,
            "newDigest": new.digest,
            "retainedRun": old_result,
            "newRun": new_result,
            "oldConfirmedCallCount": 1,
            "supervisorExitCode": supervisor.returncode,
            "automaticNewAndOldWorkers": True,
            "missingExitCode": 2,
            "tamperedExitCode": 2,
            "pythonVersion": old.python_version,
            "temporalSDK": "1.32.0",
            "scope": "retained executable bundles and real Temporal recovery; fixture worker",
        }
        (root / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)
    finally:
        for process in [*workers, server]:
            if process.poll() is None:
                process.terminate()
        for process in [*workers, server]:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    asyncio.run(main())

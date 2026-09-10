"""Fresh, owned real-provider acceptance workflow for the frozen source workspace.

The relay forwards genuine provider bytes. Boundary faults are limited to owned
Notes/relay processes; the public API creates all workflow, resource and run data.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _wait_ready(process: subprocess.Popen, output: Path, timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Owned real stack exited before readiness; inspect stack.log")
        control = output / "control.json"
        if control.exists():
            try:
                if _json(control).get("status") == "ready":
                    return
            except json.JSONDecodeError:
                pass
        time.sleep(0.2)
    raise TimeoutError("Owned real stack did not become ready")


def run_group(workspace: Path, output: Path, env: dict) -> dict:
    """Execute the real group exactly once against this workspace and new output."""
    workspace, output = workspace.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(
        (output / name).exists()
        for name in ("runs.json", "control.json", "provider-observations.jsonl")
    ):
        raise RuntimeError(
            "Real group requires fresh output; refusing to reuse previous run evidence"
        )
    if not env.get("DATABASE_URL"):
        raise RuntimeError("An explicitly owned PostgreSQL connection is required")
    if not env.get("UV_PROJECT_ENVIRONMENT"):
        raise RuntimeError("The locked Python environment is required")
    python_executable = Path(env["UV_PROJECT_ENVIRONMENT"]) / "bin/python"
    if not python_executable.is_file():
        raise RuntimeError("Locked Python interpreter is unavailable")
    helper = workspace / "backend/scripts/goal_verification/real"
    runtime_env = {
        **os.environ,
        **env,
        "GOAL_WORKSPACE": str(workspace),
        "GOAL_REAL_OUTPUT_DIR": str(output),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    stages = []

    def stage(
        label: str,
        command: list[str],
        timeout: int = 1500,
        *,
        cwd: Path | None = None,
        extra_env: dict | None = None,
    ) -> None:
        log_path = output / f"{label}.log"
        started = time.time()
        timed_out = False
        with log_path.open("w") as log:
            process = subprocess.Popen(
                command,
                cwd=cwd or workspace,
                env={**runtime_env, **(extra_env or {})},
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                # This process group contains only this stage and its descendants.
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
        stages.append(
            {
                "stage": label,
                "command": command,
                "cwd": str(cwd or workspace),
                "environmentOverrides": extra_env or {},
                "exitCode": process.returncode,
                "timedOut": timed_out,
                "elapsedSeconds": round(time.time() - started, 3),
                "log": log_path.name,
            }
        )
        (output / "stages.json").write_text(json.dumps(stages, indent=2) + "\n")
        with (output / "checks.log").open("a") as checks:
            checks.write(f"\nStage {label}: exit={process.returncode}, timeout={timed_out}\n")
            checks.write(log_path.read_text())
        if timed_out or process.returncode:
            raise RuntimeError(f"Real acceptance stage {label} failed; inspect {log_path.name}")

    def python_stage(label: str, filename: str, *args: str) -> None:
        stage(label, [str(python_executable), str(helper / filename), *args])

    def browser(phase: str) -> None:
        stage(
            "browser-" + phase,
            [
                "node",
                str(workspace / "frontend/scripts/goal-verification-browser.mjs"),
                "--phase",
                phase,
                "--base-url",
                "http://127.0.0.1:4374",
                "--api-url",
                "http://127.0.0.1:8301/api",
                "--output",
                str(output),
            ],
        )

    # Other groups may have built an absolute E2E API URL. Rebuild this same
    # frozen workspace for the owned same-origin relay before starting services.
    stage(
        "frontend-build",
        ["pnpm", "exec", "vite", "build"],
        cwd=workspace / "frontend",
        extra_env={"VITE_API_BASE_URL": "/api"},
    )
    (output / "checks.json").write_text(json.dumps({"checks": stages.copy()}, indent=2) + "\n")
    if not (workspace / "frontend/dist/index.html").is_file():
        raise RuntimeError("Frontend build did not produce index.html")
    stack = None
    try:
        with (output / "stack.log").open("w") as log:
            stack = subprocess.Popen(
                ["node", str(helper / "start.mjs")],
                cwd=workspace,
                env=runtime_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            _wait_ready(stack, output)
            for phase in ("configure", "series", "limits"):
                python_stage(phase, "acceptance.py", phase)
            python_stage("active-tools", "active_tools.py")
            python_stage("faults", "acceptance.py", "faults")
            python_stage("model-timeout", "model_timeout_probe.py")
            browser("online")
            python_stage("online-histories", "offline.py", "online-histories")
            for action, label in (
                ("stop_notes", "notes plugin"),
                ("stop_temporal", "Temporal dev server"),
            ):
                python_stage(action, "control.py", action)
                deadline = time.monotonic() + 20
                while label not in _json(output / "control.json").get("stopped", []):
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Owned service did not acknowledge {action}")
                    time.sleep(0.1)
            python_stage("double-offline", "offline.py", "double-offline")
            browser("offline")
            runs = json.loads((output / "runs.json").read_text())
            artifacts = {
                (
                    row["coreArtifact"]["artifactHash"]
                    if "artifactHash" in row["coreArtifact"]
                    else json.dumps(row["coreArtifact"], sort_keys=True)
                )
                for row in runs
            }
            assert len(artifacts) == 1, "All real runs must execute the same Core artifact"
    finally:
        if stack is not None and stack.poll() is None:
            # The launcher owns process groups, database names and runtime paths;
            # signal only that launcher so its finally path can clean them safely.
            os.kill(stack.pid, signal.SIGTERM)
            try:
                stack.wait(timeout=45)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    "Owned launcher cleanup timed out; stack remains inventoried in instance.json"
                ) from exc
    cleanup = _json(output / "cleanup.json")
    assert not cleanup["remainingDatabases"] and cleanup["ownedChildrenStopped"]
    summary = {
        "group": "real",
        "passed": True,
        "runCount": len(runs),
        "coreArtifact": runs[0]["coreArtifact"],
        "stages": stages,
        "evidence": [
            "runs.json",
            "checks.json",
            "checks.log",
            "package-baseline.json",
            "limits.json",
            "source-sets.json",
            "schedule.json",
            "include-derived.json",
            "active-tools.json",
            "read-write-faults.json",
            "provider-observations.jsonl",
            "model-timeout.json",
            "online-histories.json",
            "double-offline.json",
            "cleanup.json",
        ],
    }
    (output / "real-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    return summary

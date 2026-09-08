"""Run real target-stack acceptance using only a campaign-owned Compose project."""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from uuid import uuid4


def _ports() -> list[int]:
    sockets = [socket.socket() for _ in range(3)]
    try:
        for probe in sockets:
            probe.bind(("127.0.0.1", 0))
        return [probe.getsockname()[1] for probe in sockets]
    finally:
        for probe in sockets:
            probe.close()


# The passwords come from the isolated database container's own environment.
# Neither their values nor failed psql diagnostics are printed.
_DATABASE_ISOLATION = r"""
set -eu
for role in core finance notes; do
    case "$role" in
        core) export PGPASSWORD="$CORE_DB_PASSWORD" ;;
        finance) export PGPASSWORD="$FINANCE_DB_PASSWORD" ;;
        notes) export PGPASSWORD="$NOTES_DB_PASSWORD" ;;
    esac
    psql -h 127.0.0.1 -U "signaldeck_$role" -d "signaldeck_$role" \
        -v ON_ERROR_STOP=1 -Atc 'SELECT 1' >/dev/null 2>&1
    for target in core finance notes; do
        if [ "$role" != "$target" ]; then
            if psql -h 127.0.0.1 -U "signaldeck_$role" -d "signaldeck_$target" \
                -v ON_ERROR_STOP=1 -Atc 'SELECT 1' >/dev/null 2>&1; then
                echo "FAIL: $role can connect to $target" >&2
                exit 1
            fi
            echo "Denied cross-database connection: $role -> $target"
        fi
    done
done
"""


# Run diagnostic commands through the campaign recorder, but redact container
# output before it reaches that recorder. Secrets are read only from child env.
_DIAGNOSTICS = r"""
import os
import subprocess
import sys

try:
    result = subprocess.run(sys.argv[1:], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=60)
    output, status = result.stdout, result.returncode
except subprocess.TimeoutExpired as error:
    output, status = (error.stdout or b"") + b"\nDiagnostic capture timed out\n", 124
text = output.decode("utf-8", errors="replace")
names = ("POSTGRES_PASSWORD", "CORE_DB_PASSWORD", "FINANCE_DB_PASSWORD",
         "NOTES_DB_PASSWORD", "AGENT_PLATFORM_ENCRYPTION_KEY", "SIGNALDECK_API_TOKEN")
secrets = [os.environ.get(name, "") for name in names] + ["compose-fake-credential"]
for value in sorted(set(secrets), key=len, reverse=True):
    if value:
        text = text.replace(value, "[REDACTED]")
sys.stdout.write(text)
sys.exit(status)
"""


def run_compose(workspace: Path, evidence: Path, env: dict, run_command) -> dict:
    """Build and verify an owned stack; retain bind data for explicit owner cleanup.

    ``workspace`` must be the campaign's isolated source copy. The caller supplies
    a clean environment, an installed backend interpreter and frontend Playwright
    dependencies/browser. Every subprocess goes through its recording callback.
    """
    workspace, evidence = workspace.resolve(), evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    project = "sd-accept-" + uuid4().hex[:16]
    data = workspace / ".signaldeck-target" / project
    data.mkdir(parents=True, exist_ok=False)
    (data / "acceptance-owner.json").write_text(
        json.dumps({"project": project, "workspace": str(workspace)}) + "\n"
    )
    for directory in ("postgres", "temporal", "artifacts", "core", "core-environments", "uv-cache"):
        (data / directory).mkdir()
    app_port, finance_port, temporal_port = _ports()
    local_env = dict(env)
    local_env.update(
        COMPOSE_PROJECT_NAME=project,
        SIGNALDECK_DATA_DIR=str(data),
        SIGNALDECK_LOCAL_IMAGE_PREFIX=project,
        SIGNALDECK_LOCAL_UID=str(os.getuid()),
        SIGNALDECK_LOCAL_GID=str(os.getgid()),
        SIGNALDECK_PLUGINS="finance,digital-oracle,notes",
        SIGNALDECK_API_TOKEN="",
        AGENT_PLATFORM_ENCRYPTION_KEY=uuid4().hex,
        POSTGRES_PASSWORD=uuid4().hex,
        CORE_DB_PASSWORD=uuid4().hex,
        FINANCE_DB_PASSWORD=uuid4().hex,
        NOTES_DB_PASSWORD=uuid4().hex,
        APP_PORT=str(app_port),
        FINANCE_PORT=str(finance_port),
        TEMPORAL_UI_PORT=str(temporal_port),
        FRED_API_KEY="",
        EDGAR_CONTACT_EMAIL="",
    )
    compose = [
        "docker",
        "compose",
        "--env-file",
        os.devnull,
        "--project-name",
        project,
        "-f",
        "docker-compose.yml",
        "-f",
        "docker/compose.acceptance.yml",
        "--profile",
        "finance",
        "--profile",
        "digital-oracle",
        "--profile",
        "notes",
    ]
    report = {
        "status": "running",
        "project": project,
        "dataDirectory": str(data),
        "imagePrefix": project,
        "commands": [],
        "checks": [],
        "diagnostics": [],
        "cleanup": {"containersRemoved": False, "dataRetained": True, "imagesRetained": True},
    }

    def command(argv, name, timeout=1800):
        record = run_command(argv, workspace, env=local_env, timeout=timeout, name=name)
        report["commands"].append(record)

    failure = None
    try:
        command(compose + ["build", "app", "finance", "digital-oracle", "notes"], "compose-build")
        command(
            compose
            + [
                "up",
                "--detach",
                "--wait",
                "--wait-timeout",
                "240",
                "app",
                "worker",
                "dispatcher",
                "finance",
                "digital-oracle",
                "notes",
                "fake-model",
            ],
            "compose-up",
        )
        command(compose + ["run", "--rm", "bootstrap"], "compose-bootstrap")
        command(
            compose + ["exec", "-T", "db", "sh", "-c", _DATABASE_ISOLATION], "compose-db-isolation"
        )
        report["checks"].append(
            "three owning database roles and six denied cross-database connections"
        )
        python = workspace / "backend/.venv/bin/python"
        verify = [
            str(python) if python.is_file() else sys.executable,
            str(workspace / "docker/verify_target_stack.py"),
            "--base-url",
            f"http://localhost:{app_port}",
            "--finance-url",
            f"http://localhost:{finance_port}",
            "--evidence",
            str(evidence / "compose.json"),
        ]
        command(verify, "compose-api-acceptance")
        command(
            [
                "node",
                str(workspace / "docker/inspect_target_ui.mjs"),
                str(evidence / "compose.json"),
                str(evidence),
            ],
            "compose-browser-acceptance",
        )
        report["checks"].extend(json.loads((evidence / "compose.json").read_text())["checks"])
        report["checks"].extend(json.loads((evidence / "ui.json").read_text())["checks"])
        command(
            compose
            + [
                "stop",
                "worker",
                "dispatcher",
                "temporal",
                "finance",
                "digital-oracle",
                "notes",
                "fake-model",
            ],
            "compose-stop-execution",
        )
        command(verify + ["--read-only"], "compose-offline-history")
        report["checks"].append(
            "historical runs and artifacts readable with all execution dependencies stopped"
        )
    except BaseException as exc:
        failure = exc
        report["status"] = "failed"
        report["failureType"] = type(exc).__name__
        raise
    finally:
        diagnostic_failure = None
        for name, arguments in (
            ("compose-diagnostic-ps", ["ps", "--all"]),
            ("compose-diagnostic-logs", ["logs", "--no-color"]),
        ):
            diagnostic = {"command": name, "status": "running"}
            report["diagnostics"].append(diagnostic)
            try:
                command(
                    [sys.executable, "-c", _DIAGNOSTICS, *compose, *arguments],
                    name,
                    timeout=90,
                )
                diagnostic["status"] = "captured"
                diagnostic["log"] = report["commands"][-1]["log"]
            except BaseException as error:
                diagnostic["status"] = "failed"
                diagnostic["failureType"] = type(error).__name__
                diagnostic_failure = error
                if failure is not None:
                    failure.add_note(f"{name} also failed; inspect command logs")
        try:
            command(compose + ["down", "--timeout", "30", "--remove-orphans"], "compose-cleanup")
            report["cleanup"]["containersRemoved"] = True
            report["cleanup"]["action"] = "owned project down; bind data and unique images retained"
            if failure is None:
                report["status"] = "passed" if diagnostic_failure is None else "failed"
                if diagnostic_failure is not None:
                    report["failureType"] = "DiagnosticCaptureFailed"
        except BaseException as cleanup_error:
            report["status"] = "failed"
            report["cleanup"]["failureType"] = type(cleanup_error).__name__
            if failure is not None:
                failure.add_note(
                    "Owned Compose cleanup also failed; "
                    "inspect compose-adapter.json and command logs"
                )
            else:
                raise
        finally:
            (evidence / "compose-adapter.json").write_text(json.dumps(report, indent=2) + "\n")
        if failure is None and diagnostic_failure is not None:
            raise RuntimeError(
                "Compose diagnostics incomplete; inspect command logs"
            ) from diagnostic_failure
    return report

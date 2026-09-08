#!/usr/bin/env python3
"""Run fresh, isolated acceptance recipes and retain their command evidence."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import signal
import stat
import subprocess
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

SOURCE = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(source: Path, destination: Path, run_command) -> dict:
    listed = run_command(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        source,
        name="source-files",
    )
    paths = Path(listed["log"]).read_bytes().split(b"\0")
    manifest = []
    for raw in sorted(set(paths)):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe Git path: {relative}")
        if relative.parts[0] in {".steward", ".git", "build"}:
            continue
        original = source / relative
        if not original.exists() and not original.is_symlink():
            continue  # A tracked deletion is part of the current worktree.
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        info = original.lstat()
        if stat.S_ISLNK(info.st_mode):
            link = os.readlink(original)
            if Path(link).is_absolute() or not original.resolve().is_relative_to(source):
                raise ValueError(f"Snapshot cannot include an external symlink: {relative}")
            target.symlink_to(link)
            content = os.fsencode(link)
            kind = "symlink"
        elif stat.S_ISREG(info.st_mode):
            content = original.read_bytes()
            target.write_bytes(content)
            target.chmod(stat.S_IMODE(info.st_mode))
            kind = "file"
        else:
            raise ValueError(f"Unsupported Git-visible entry: {relative}")
        manifest.append(
            {
                "path": relative.as_posix(),
                "kind": kind,
                "mode": stat.S_IMODE(info.st_mode),
                "sha256": digest(content),
            }
        )
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return {
        "source": str(source),
        "workspace": str(destination),
        "sha256": digest(encoded),
        "files": manifest,
    }


def test_environment(workspace: Path, run_command) -> dict[str, str]:
    # Do not inherit model keys, application settings or telemetry configuration.
    allowed = {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "SYSTEMROOT",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "UV_CACHE_DIR": str(workspace / ".uv-cache"),
            "UV_PROJECT_ENVIRONMENT": str(workspace / "backend" / ".venv"),
            "LOGFIRE_SEND_TO_LOGFIRE": "false",
            "OTEL_TRACES_EXPORTER": "none",
            "OTEL_METRICS_EXPORTER": "none",
            "OTEL_LOGS_EXPORTER": "none",
            "TEMPORAL_CLI": os.environ.get("TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"),
        }
    )
    database = os.environ.get("CLOSED_LOOP_TEST_DATABASE_URL") or os.environ.get(
        "TEST_DATABASE_URL"
    )
    if not database:
        result = run_command(
            [
                "docker",
                "port",
                os.environ.get("CLOSED_LOOP_POSTGRES_CONTAINER", "signaldeck-target-test-postgres"),
                "5432/tcp",
            ],
            workspace,
            env=env,
            name="test-postgres-port",
        )
        port = Path(result["log"]).read_text().splitlines()[0].rsplit(":", 1)[-1]
        if not port.isdecimal():
            raise ValueError("Dedicated test PostgreSQL did not report a numeric port")
        database = f"postgresql+psycopg://signaldeck:signaldeck@127.0.0.1:{port}/signaldeck"
    parsed = urlsplit(database)
    if parsed.scheme not in {
        "postgresql",
        "postgresql+psycopg",
        "postgres",
    } or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Acceptance requires an explicitly local test PostgreSQL URL")
    env["TEST_DATABASE_URL"] = database
    env["DATABASE_URL"] = database
    env["CLOSED_LOOP_SOURCE_ROOT"] = str(SOURCE)
    env["RECOVERY_POSTGRES_CONTAINER"] = os.environ.get(
        "CLOSED_LOOP_POSTGRES_CONTAINER", "signaldeck-target-test-postgres"
    )
    return env


def assertion_sources(workspace: Path, paths: list[str]) -> list[dict]:
    result = []
    for relative in paths:
        path = workspace / relative
        data = path.read_bytes()
        text = data.decode("utf-8")
        module = ast.parse(text, filename=relative)
        for node in ast.walk(module):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                result.append(
                    {
                        "path": relative,
                        "sha256": digest(data),
                        "function": node.name,
                        "line": node.lineno,
                        "endLine": node.end_lineno,
                        "assertions": [
                            {"line": child.lineno, "text": ast.get_source_segment(text, child)}
                            for child in ast.walk(node)
                            if isinstance(child, ast.Assert)
                        ],
                    }
                )
    return result


def junit_results(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    result = []
    for node in root.iter("testcase"):
        status = "passed"
        for tag in ("skipped", "failure", "error"):
            if node.find(tag) is not None:
                status = tag
        result.append(
            {
                "name": node.get("name"),
                "className": node.get("classname"),
                "seconds": node.get("time"),
                "status": status,
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    args = parser.parse_args()
    raw_evidence = os.environ.get("CLOSED_LOOP_EVIDENCE_DIR")
    if not raw_evidence:
        parser.error("CLOSED_LOOP_EVIDENCE_DIR must name this invocation's evidence directory")
    evidence = Path(raw_evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    if any((evidence / name).exists() for name in ("observations.json", "checks.txt")):
        parser.error("Evidence already exists; each invocation requires a fresh directory")
    checks = evidence / "checks.txt"
    checks.write_text("Fresh isolated acceptance invocation\n", encoding="utf-8")
    observations = {
        "case": args.case,
        "startedAt": time.time(),
        "status": "running",
        "commands": [],
    }
    environment = None

    def save() -> None:
        write_json(evidence / "observations.json", observations)

    def run_command(
        argv: list[str],
        cwd: Path,
        *,
        env: dict | None = None,
        timeout: int = 1800,
        name: str | None = None,
    ) -> dict:
        sequence = len(observations["commands"]) + 1
        label = name or Path(argv[0]).name
        safe_label = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)
        log = evidence / f"{sequence:03d}-{safe_label}.log"
        record = {
            "argv": [str(value) for value in argv],
            "cwd": str(cwd),
            "log": str(log),
            "startedAt": time.time(),
            "exitCode": None,
        }
        observations["commands"].append(record)
        save()
        with checks.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        start = time.monotonic()
        process = None
        try:
            with log.open("wb") as output:
                process = subprocess.Popen(
                    record["argv"],
                    cwd=cwd,
                    env=env if env is not None else environment,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    record["exitCode"] = process.wait(timeout=timeout)
                except BaseException:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    record["exitCode"] = process.returncode
                    raise
        except BaseException as error:
            record["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            record["seconds"] = time.monotonic() - start
            with checks.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            save()
        if record["exitCode"] != 0:
            raise RuntimeError(f"Command {label} exited {record['exitCode']}; see {log.name}")
        return record

    save()
    try:
        recipes = json.loads((SOURCE / "backend/scripts/acceptance_recipes.json").read_text())
        recipe = recipes["cases"][args.case]
        observations["recipe"] = recipe
        # TemporaryDirectory removes only its own tree and does not follow directory symlinks.
        temporary_parent = Path.home() / ".cache/signaldeck-acceptance"
        temporary_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f"sd-acceptance-{args.case}-", dir=temporary_parent
        ) as temporary:
            workspace = Path(temporary) / "source"
            workspace.mkdir()
            identity = snapshot(SOURCE, workspace, run_command)
            write_json(evidence / "source-manifest.json", identity)
            observations["sourceSnapshot"] = {
                key: value for key, value in identity.items() if key != "files"
            }
            observations["sourceSnapshot"]["fileCount"] = len(identity["files"])
            environment = test_environment(workspace, run_command)
            environment["SIGNALDECK_CANCEL_DIAGNOSTICS"] = str(evidence / "repeat-cancel-history")
            observations["testEnvironment"] = {
                "databaseHost": urlsplit(environment["TEST_DATABASE_URL"]).hostname,
                "temporalCli": environment["TEMPORAL_CLI"],
                "externalModels": "not configured",
                "telemetry": "external exporters disabled",
            }
            run_command(
                ["uv", "sync", "--frozen", "--python", "3.13.13"],
                workspace / "backend",
                name="uv-sync",
            )
            paths = recipe["pytestFiles"]
            observations["tests"] = assertion_sources(workspace, paths)
            save()
            if paths:
                junit = evidence / "pytest.xml"
                try:
                    run_command(
                        [
                            "uv",
                            "run",
                            "--frozen",
                            "pytest",
                            *[str(Path(p).relative_to("backend")) for p in paths],
                            f"--junitxml={junit}",
                            f"--basetemp={workspace / '.pytest-tmp'}",
                        ],
                        workspace / "backend",
                        name="pytest",
                        timeout=3600,
                    )
                finally:
                    if junit.exists():
                        observations["junitCases"] = junit_results(junit)
                        save()
                cases = observations.get("junitCases", [])
                if not cases or any(case["status"] != "passed" for case in cases):
                    raise RuntimeError(
                        "Pytest must execute tests with no failures, errors or skips"
                    )
            extras_path = workspace / "backend/scripts/acceptance_extras.py"
            spec = importlib.util.spec_from_file_location("acceptance_extras", extras_path)
            if spec is None or spec.loader is None:
                raise RuntimeError("Cannot load acceptance_extras from the source snapshot")
            import sys

            sys.path.insert(0, str(extras_path.parent))
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            observations["extra"] = module.run_extra(
                args.case, workspace, evidence, environment, run_command
            )
            for filename in recipe["requiredFiles"]:
                path = evidence / filename
                if not path.is_file() or path.stat().st_size == 0:
                    raise RuntimeError(f"Missing nonempty required evidence: {filename}")
            observations["status"] = "passed"
    except BaseException as error:
        observations["status"] = "failed"
        observations["error"] = f"{type(error).__name__}: {error}"
        (evidence / "runner-error.log").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        observations["finishedAt"] = time.time()
        save()
    return 0 if observations["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

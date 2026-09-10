"""Execute native suites against a caller-owned source copy; retain fresh evidence."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit


def _junit(path: Path) -> list[str]:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError("JUnit contains no test cases")
    for suite in root.iter():
        if suite.tag in {"testsuite", "testsuites"}:
            for field in ("failures", "errors", "skipped", "disabled"):
                if int(suite.get(field, "0")):
                    raise ValueError(f"JUnit reports nonzero {field}")
    names = []
    for case in cases:
        if any(case.find(tag) is not None for tag in ("failure", "error", "skipped")):
            raise ValueError(f"JUnit test did not pass: {case.get('name')}")
        names.append(f"{case.get('classname', '')}::{case.get('name', '')}")
    return names


def _playwright(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    stats = data["stats"]
    if stats["expected"] <= 0 or any(stats[key] for key in ("unexpected", "flaky", "skipped")):
        raise ValueError(f"Playwright did not pass cleanly: {stats}")
    if data.get("errors"):
        raise ValueError("Playwright reported suite errors")
    names = []

    def visit(suites: list[dict]) -> None:
        for suite in suites:
            for spec in suite.get("specs", []):
                tests = spec.get("tests", [])
                if not spec["ok"] or not tests:
                    raise ValueError(f"Playwright spec did not pass: {spec['title']}")
                for test in tests:
                    results = test.get("results", [])
                    if (
                        test["status"] != "expected"
                        or test["expectedStatus"] != "passed"
                        or not results
                        or any(result["status"] != "passed" for result in results)
                    ):
                        raise ValueError(f"Playwright test did not pass: {spec['title']}")
                    names.append(f"{spec['file']}::{spec['title']}[{test.get('projectName', '')}]")
            visit(suite.get("suites", []))

    visit(data["suites"])
    if not names or len(names) != stats["expected"]:
        raise ValueError("Playwright case count does not match successful test count")
    return names


def _owned_stop(process: subprocess.Popen) -> None:
    # start_new_session makes this invocation the leader of the only group we signal.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=10)


def _run(
    argv: list[str], cwd: Path, output: Path, env: dict[str, str], timeout: int, index: int
) -> dict:
    log = output / f"{index:02d}-{Path(argv[0]).name}.log"
    record = {
        "argv": argv,
        "cwd": str(cwd),
        "log": str(log),
        "timeoutSeconds": timeout,
        "startedAt": time.time(),
        "exitCode": None,
        "timedOut": False,
    }
    process = None
    start = time.monotonic()
    try:
        with log.open("wb") as stream:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                record["exitCode"] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record["timedOut"] = True
                _owned_stop(process)
                record["exitCode"] = process.returncode
    except BaseException as error:
        if process is not None:
            _owned_stop(process)
        record["error"] = f"{type(error).__name__}: {error}"
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        record["seconds"] = time.monotonic() - start
        with (output / "checks.log").open("a", encoding="utf-8") as checks:
            checks.write(json.dumps(record, ensure_ascii=False) + "\n")
            if log.exists():
                with log.open(encoding="utf-8", errors="replace") as captured:
                    shutil.copyfileobj(captured, checks)
                checks.write("\n")
    return record


def _produced_files(workspace: Path) -> dict[Path, tuple[int, int, int]]:
    files = {}
    for root in (workspace / "output/playwright", workspace / "frontend/test-results"):
        if not root.exists():
            continue
        if root.is_symlink():
            raise ValueError(f"Evidence root is a symlink: {root}")
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"Evidence path is a symlink: {path}")
            if path.is_file():
                stat = path.stat()
                files[path] = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
    return files


def _commands(group: str, workspace: Path, output: Path, env: dict[str, str]) -> list[tuple]:
    python = str(Path(env["UV_PROJECT_ENVIRONMENT"]) / "bin/python")
    backend, frontend = workspace / "backend", workspace / "frontend"
    xml = f"--junitxml={output / 'tests.xml'}"
    if group == "backend":
        return [(backend, [python, "-m", "pytest", xml], 3600)]
    if group == "finance":
        env["PYTHONPATH"] = os.pathsep.join(
            str(workspace / path) for path in ("plugins/finance", "plugins/runtime")
        )
        return [
            (
                workspace,
                [
                    python,
                    "-m",
                    "pytest",
                    "plugins/finance/tests/test_finance_ux.py",
                    "-q",
                    "-s",
                    xml,
                ],
                1800,
            )
        ]
    if group == "frontend":
        return [
            (
                frontend,
                [
                    "pnpm",
                    "exec",
                    "vitest",
                    "run",
                    "--reporter=junit",
                    f"--outputFile={output / 'tests.xml'}",
                ],
                1800,
            )
        ]
    if group in {"e2e", "fault"}:
        env["PLAYWRIGHT_JSON_OUTPUT_FILE"] = str(output / "tests.json")
        env["PLAYWRIGHT_HTML_OPEN"] = "never"
        argv = [
            "pnpm",
            "exec",
            "playwright",
            "test",
            "--workers=1",
            "--reporter=json",
            "--forbid-only",
            "--retries=0",
        ]
        if group == "fault":
            argv.extend(["--config", "playwright.fault.config.ts"])
        return [(frontend, argv, 3600)]
    if group == "static":
        # This process only parses Compose with explicit dummy values, never a real .env.
        env.update(
            {
                "DATABASE_URL": "postgresql://example:example@db:5432/example",
                "TEMPORAL_ADDRESS": "temporal:7233",
                "AGENT_PLATFORM_ENCRYPTION_KEY": "acceptance-example-only",
                "SIGNALDECK_API_TOKEN": "acceptance-example-only",
                "SIGNALDECK_IMAGE_TAG": "acceptance-example-only",
            }
        )
        commands = [
            (backend, [python, "-m", *args], 600)
            for args in (
                ["ruff", "check", "app", "tests"],
                ["black", "--check", "app", "tests"],
                ["isort", "--check-only", "app", "tests"],
                ["mypy", "app"],
            )
        ]
        commands.extend((frontend, ["pnpm", task], 600) for task in ("lint", "typecheck", "build"))
        commands.extend(
            (
                workspace,
                [
                    "docker",
                    "compose",
                    "--env-file",
                    os.devnull,
                    "-f",
                    filename,
                    "config",
                    "--quiet",
                ],
                120,
            )
            for filename in ("docker-compose.yml", "docker/compose.production.example.yml")
        )
        return commands
    if group == "runner-check":
        env["PYTHONPYCACHEPREFIX"] = str(workspace / ".verification-pycache")
        files = sorted((backend / "scripts/goal_verification").rglob("*.py"))
        files.extend(sorted((backend / "scripts").glob("*goal*case*.py")))
        scripts = sorted((frontend / "scripts").glob("goal-verification*.mjs"))
        scripts.extend(sorted((backend / "scripts/goal_verification").rglob("*.mjs")))
        if not files:
            raise ValueError("No verification Python modules found")
        return [
            (workspace, [python, "-m", "py_compile", *map(str, files)], 120),
            *((workspace, ["node", "--check", str(path)], 120) for path in scripts),
        ]
    raise ValueError(f"Unknown native group: {group}")


def run_group(group: str, workspace: Path, output: Path, env: dict[str, str]) -> dict:
    """Run one native group without caches; failures remain visible in returned evidence.

    The caller owns source identity, dependencies, database lifecycle and serialization
    of E2E invocations (whose existing harness binds fixed API/frontend ports).
    A group output must be fresh. Only files produced or changed during this call are
    copied from the workspace; existing reports are never accepted as test results.
    """
    workspace, output = workspace.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Native group requires an empty output directory")
    (output / "checks.log").touch()
    result = {
        "group": group,
        "passed": False,
        "testNames": [],
        "commands": [],
        "artifacts": [],
        "errors": [],
        "startedAt": time.time(),
    }
    before = None
    try:
        if not workspace.is_dir():
            raise ValueError("Source workspace does not exist")
        environment = dict(env)
        if group in {"backend", "finance", "e2e", "fault"}:
            for key in ("TEST_DATABASE_URL", "DATABASE_URL"):
                parsed = urlsplit(environment[key])
                if parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgres"} or (
                    parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                ):
                    raise ValueError(f"{key} must refer to the caller-owned local PostgreSQL")
        environment["PATH"] = str(Path(environment["UV_PROJECT_ENVIRONMENT"]) / "bin") + (
            os.pathsep + environment.get("PATH", os.defpath)
        )
        before = _produced_files(workspace)
        commands = _commands(group, workspace, output, environment)
        for index, (cwd, argv, timeout) in enumerate(commands, 1):
            command = _run(argv, cwd, output, environment, timeout, index)
            result["commands"].append(command)
            if command["exitCode"] != 0 or command["timedOut"] or command.get("error"):
                result["errors"].append(f"Command {index} failed; see {Path(command['log']).name}")
        if group in {"backend", "frontend", "finance"}:
            result["testNames"] = _junit(output / "tests.xml")
        elif group in {"e2e", "fault"}:
            result["testNames"] = _playwright(output / "tests.json")
    except BaseException as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
        if not isinstance(error, Exception):
            raise
    finally:
        if before is not None:
            try:
                for path, fingerprint in _produced_files(workspace).items():
                    if before.get(path) == fingerprint:
                        continue
                    if path.is_relative_to(workspace / "output/playwright"):
                        relative = Path("playwright") / path.relative_to(
                            workspace / "output/playwright"
                        )
                    else:
                        relative = Path("test-results") / path.relative_to(
                            workspace / "frontend/test-results"
                        )
                    target = output / "outputs" / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
            except Exception as error:
                result["errors"].append(f"Artifact copy failed: {type(error).__name__}: {error}")
        result["finishedAt"] = time.time()
        result["passed"] = bool(result["commands"]) and not result["errors"]
        result["artifacts"] = [
            str(path.relative_to(output)) for path in sorted(output.rglob("*")) if path.is_file()
        ]
        (output / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return result

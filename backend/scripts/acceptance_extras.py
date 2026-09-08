"""Existing integration and quality commands bound to closed-loop case evidence."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

UI_CASES = {
    "A04": (["workflow-packages.spec.ts"], "definition-graph.png"),
    "A06": (["runs.spec.ts"], "cancelled-run.png"),
    "A09": (["runs.spec.ts", "workflow-packages.spec.ts"], "cancelled-run.png"),
    "A11": (["workflow-packages.spec.ts", "scheduled-tasks.spec.ts"], "call-evidence.png"),
    "A15": (["workflow-packages.spec.ts"], "call-evidence.png"),
    "A17": (["scheduled-tasks.spec.ts"], None),
}
RECOVERY_CASES = {"A01", "A07", "A10", "A14", "A15", "A16"}


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _unlock_owned(path: Path) -> None:
    # Published execution closures are intentionally read-only. Touch only an owned tree.
    if path.is_symlink():
        return
    if path.is_dir():
        path.chmod(path.stat().st_mode | 0o700)
        for child in path.iterdir():
            _unlock_owned(child)
    elif path.exists():
        path.chmod(path.stat().st_mode | 0o600)


def _frontend(workspace, evidence, env, run_command, specs=None):
    frontend = workspace / "frontend"
    run_command(["pnpm", "install", "--frozen-lockfile"], frontend, name="frontend-install")
    config = evidence / "playwright.config.ts"
    original = frontend / "playwright.config.ts"
    config.write_text(
        "import base from " + json.dumps(str(original)) + ";\n"
        "export default {...base, testDir: " + json.dumps(str(frontend / "e2e")) + ","
        "outputDir: " + json.dumps(str(evidence / "browser-results")) + ","
        "reporter: [['json', {outputFile: " + json.dumps(str(evidence / "browser.json")) + "}]],"
        "webServer: base.webServer.map(server => ({...server, cwd: "
        + json.dumps(str(frontend))
        + "})),"
        "use: {...base.use, screenshot: 'on'}};\n"
    )
    run_command(
        ["pnpm", "exec", "playwright", "test", "--config", str(config), *(specs or [])],
        frontend,
        timeout=1800,
        name="browser",
    )
    result = json.loads((evidence / "browser.json").read_text())
    stats = result["stats"]
    if stats["unexpected"] or stats["skipped"] or not stats["expected"]:
        raise AssertionError(f"Browser cases incomplete: {stats}")
    return {"stats": stats, "report": "browser.json"}


def _recovery(workspace, evidence, env, run_command):
    temporary_root = workspace / ".recovery-tmp"
    temporary_root.mkdir()
    child_env = {**env, "PYTHONPATH": str(workspace / "backend"), "TMPDIR": str(temporary_root)}
    wrapper = (
        "import runpy, signal, sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(sys.argv[1]).parent))\n"
        "def stop(signum, frame):\n    raise SystemExit(143)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "runpy.run_path(sys.argv[1], run_name='__main__')\n"
    )
    report_root = workspace / ".steward/goals/sd-target-001/verification/platform-recovery"
    try:
        run_command(
            [
                str(workspace / "backend/.venv/bin/python"),
                "-B",
                "-c",
                wrapper,
                str(workspace / "backend/scripts/verify_platform_recovery.py"),
            ],
            workspace,
            env=child_env,
            timeout=1800,
            name="core-plugin-recovery",
        )
    finally:
        reports = list(report_root.glob("*/report.json"))
        for report in reports:
            destination = evidence / "product-recovery"
            if len(reports) != 1:
                destination = evidence / ("product-recovery-" + report.parent.name)
            shutil.copytree(report.parent, destination)
        _unlock_owned(temporary_root)
    if len(reports) != 1:
        raise AssertionError("Recovery script did not produce exactly one fresh report")
    record = json.loads(reports[0].read_text())
    if record.get("status") != "passed":
        raise AssertionError("Product recovery was not confirmed")
    if not record.get("ownedWorkersStopped") or not record.get("ownedDatabasesRemoved"):
        raise AssertionError("Recovery did not clean its owned processes/databases")
    owned = Path(record["workDirectory"])
    if owned.parent.resolve() != temporary_root.resolve():
        raise AssertionError("Unexpected recovery directory owner")
    shutil.rmtree(owned)
    return {
        "report": "product-recovery/report.json",
        "status": record["status"],
        "checks": {
            key: record.get(key)
            for key in (
                "oldConfirmedModelCalls",
                "oldWriteEffects",
                "fullProductWorkerRecovery",
                "sameCorePluginUpgrade",
                "wireSecretAbsenceChecked",
                "sourceSnapshotUnchanged",
            )
        },
        "fixtureLimitations": record.get("unverified", []),
    }


def _comparison(source_root, workspace, evidence):
    archive = source_root / ".steward/archives/sd-target-001-implementation/verification/cases/A16"
    metadata = json.loads((archive / "observations.json").read_text())
    comparison_files = [
        "temporal-evidence.json",
        "prefect-crash_ownership_probe-report.json",
        "prefect-probe-report.json",
        "prefect-cancel_probe-report.json",
        "prefect-auto_recovery_probe-report.json",
        "hatchet-report.json",
    ]
    copied = []
    for name in comparison_files:
        source = archive / name
        data = source.read_bytes()
        json.loads(data)
        (evidence / name).write_bytes(data)
        copied.append({"file": name, "sha256": hashlib.sha256(data).hexdigest()})
    document = workspace / "docs/执行引擎比较.md"
    text = document.read_text()
    for name in ("Temporal", "Prefect", "Hatchet"):
        if name not in text:
            raise AssertionError(f"Comparison omits {name}")
    (evidence / "engine-comparison.md").write_text(text)
    # These remain explicitly historical observations, never fresh product case results.
    return {
        "comparisonKind": "retained candidate experiments",
        "files": copied,
        "originalCase": metadata.get("criterion"),
        "currentProductIntegration": "product-recovery/report.json",
        "limitationsPreservedIn": "engine-comparison.md",
    }


def _domain_imports(workspace):
    prohibited = (
        "fastapi",
        "sqlalchemy",
        "mcp",
        "temporalio",
        "plugins",
        "app.infrastructure",
        "app.api",
    )
    inspected = []
    for directory in ("domain", "application"):
        for path in sorted((workspace / "backend/app" / directory).glob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                imports = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else [item.name for item in node.names] if isinstance(node, ast.Import) else []
                )
                for name in imports:
                    if any(
                        name == prefix or name.startswith(prefix + ".") for prefix in prohibited
                    ):
                        raise AssertionError(f"Concrete dependency in {path}: {name}")
            inspected.append(str(path.relative_to(workspace)))
    return {"inspected": inspected, "prohibitedConcreteImports": list(prohibited)}


def _quality(workspace, evidence, env, run_command):
    backend = workspace / "backend"
    commands = [
        ["uv", "run", "--frozen", "ruff", "check", "app", "tests"],
        ["uv", "run", "--frozen", "black", "--check", "app", "tests"],
        ["uv", "run", "--frozen", "isort", "--check-only", "app", "tests"],
        ["uv", "run", "--frozen", "mypy", "app"],
        ["uv", "run", "--frozen", "pytest", "--junitxml=" + str(evidence / "full-backend.xml")],
    ]
    for index, command in enumerate(commands):
        run_command(command, backend, timeout=1800, name=f"backend-quality-{index}")
    import xml.etree.ElementTree as ET

    tree = ET.parse(evidence / "full-backend.xml")
    cases = tree.findall(".//testcase")
    if not cases or any(c.find("skipped") is not None for c in cases):
        raise AssertionError("Backend quality sweep has missing/skipped cases")
    frontend = workspace / "frontend"
    run_command(["pnpm", "install", "--frozen-lockfile"], frontend, name="frontend-install")
    for command in ("lint", "typecheck", "build", "test:run"):
        run_command(["pnpm", command], frontend, name="frontend-" + command.replace(":", "-"))
    browser = _frontend(workspace, evidence, env, run_command)
    run_command(["docker", "build", "."], workspace, timeout=2400, name="root-image-build")
    import tomllib

    backend_version = tomllib.loads((backend / "pyproject.toml").read_text())["project"]["version"]
    frontend_version = json.loads((frontend / "package.json").read_text())["version"]
    assert (backend / "VERSION").read_text().strip() == backend_version
    assert (frontend / "VERSION").read_text().strip() == frontend_version
    run_command(
        ["uv", "run", "--frozen", "pytest", "tests/test_target_seeds.py"],
        backend,
        name="demo-contracts",
    )
    dependencies = _domain_imports(workspace)
    review = [
        "# Project completion observations",
        "",
        f"Backend cases: {len(cases)}; no skips.",
        f"Frontend E2E: {browser['stats']}.",
        f"Version files agree: backend {backend_version}, frontend {frontend_version}.",
        "Actual quality/build commands, exit status and raw logs are in checks.txt.",
        "Domain/application checks inspected the files listed in observations.json.",
        "Existing instances were not switched or reset; only owned test resources were used.",
        "The verifier separately reviews source/evidence findings; "
        "passing commands do not adjudicate untested target assertions.",
    ]
    (evidence / "delivery-review.md").write_text("\n".join(review) + "\n")
    return {
        "backendCases": len(cases),
        "browser": browser,
        "dependencyChecks": dependencies,
        "versions": {"backend": backend_version, "frontend": frontend_version},
    }


def run_extra(case, workspace, evidence, env, run_command):
    extra = {}
    if case in UI_CASES:
        specs, screenshot = UI_CASES[case]
        extra["browser"] = _frontend(workspace, evidence, env, run_command, specs)
        if screenshot is not None:
            images = list((evidence / "browser-results").rglob(screenshot))
            if not images:
                raise AssertionError("Verified browser screenshot missing: " + screenshot)
            shutil.copyfile(images[0], evidence / "ui.png")
            extra["screenshot"] = "ui.png"
    if case in RECOVERY_CASES:
        extra["recovery"] = _recovery(workspace, evidence, env, run_command)
    if case == "A16":
        extra["comparison"] = _comparison(Path(env["CLOSED_LOOP_SOURCE_ROOT"]), workspace, evidence)
    if case == "A18":
        extra["dependencies"] = _domain_imports(workspace)
    if case in {"A14", "local-workflow-loop"}:
        from acceptance_compose import run_compose

        run_command(
            ["pnpm", "install", "--frozen-lockfile"],
            workspace / "frontend",
            name="compose-browser-install",
        )
        extra["compose"] = run_compose(workspace, evidence, env, run_command)
    if case == "project-completion":
        extra["quality"] = _quality(workspace, evidence, env, run_command)
    return extra

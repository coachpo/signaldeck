"""Opt-in, paired ablations using the repository's isolated PostgreSQL fixtures."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.conftest import _isolate_api_token_env as _isolate_api_token_env
from tests.conftest import database_url as database_url
from tests.conftest import session_factory as session_factory

ROOT = Path(__file__).resolve().parents[3]
ROWS: list[dict] = []
OUTCOMES: list[dict] = []
ENVIRONMENT: dict[str, str] = {}
SOURCE_MANIFEST: dict[str, str] = {}
STARTED_AT = ""


def source_manifest():
    paths = [
        *sorted((ROOT / "backend/app").rglob("*.py")),
        *sorted((ROOT / "backend/tests").rglob("*.py")),
        *sorted((ROOT / "backend/experiments/ablation").glob("*.py")),
        ROOT / "backend/uv.lock",
    ]
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    }


def pytest_sessionstart(session):
    global STARTED_AT
    if session.config.getoption("--run-ablation"):
        SOURCE_MANIFEST.update(source_manifest())
        STARTED_AT = datetime.now(UTC).isoformat()


def pytest_addoption(parser):
    group = parser.getgroup("ablation")
    group.addoption("--run-ablation", action="store_true", help="Run isolated ablation workloads")
    group.addoption("--ablation-samples", type=int, default=5)
    group.addoption("--ablation-output", default="results/ablation/metrics.json")


def pytest_ignore_collect(collection_path, config):
    if collection_path.name.startswith("test_") and not config.getoption("--run-ablation"):
        return True
    return None


def pytest_generate_tests(metafunc):
    if {"sample", "variant"} <= set(metafunc.fixturenames):
        samples = metafunc.config.getoption("--ablation-samples")
        if samples < 1:
            raise pytest.UsageError("--ablation-samples must be positive")
        # Alternate order to reduce systematic cold-start / host-load bias.
        pairs = [
            (sample, variant)
            for sample in range(samples)
            for variant in (("baseline", "ablated") if sample % 2 == 0 else ("ablated", "baseline"))
        ]
        metafunc.parametrize("sample,variant", pairs)


@pytest.fixture
def record(request):
    def append(row):
        ROWS.append({"test": request.node.nodeid, **row})

    return append


@pytest.fixture(autouse=True)
def database_version(session_factory):
    if not ENVIRONMENT:
        with session_factory() as session:
            ENVIRONMENT["postgresql"] = session.scalar(text("SELECT version()"))


def pytest_runtest_logreport(report):
    if "experiments/ablation/" in report.nodeid and (
        report.when == "call" or report.failed or report.skipped
    ):
        OUTCOMES.append({"test": report.nodeid, "phase": report.when, "outcome": report.outcome})


def pytest_sessionfinish(session, exitstatus):
    if not session.config.getoption("--run-ablation"):
        return
    final_manifest = source_manifest()
    drift = sorted(
        path
        for path in SOURCE_MANIFEST.keys() | final_manifest.keys()
        if SOURCE_MANIFEST.get(path) != final_manifest.get(path)
    )
    if drift:
        session.exitstatus = exitstatus = pytest.ExitCode.TESTS_FAILED
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True).splitlines()
    output = Path(session.config.getoption("--ablation-output")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "started_at": STARTED_AT,
                "completed_at": datetime.now(UTC).isoformat(),
                "revision": revision,
                "working_tree": dirty,
                "python": sys.version,
                "platform": platform.platform(),
                "environment": ENVIRONMENT,
                "dependencies": {
                    name: importlib.metadata.version(name)
                    for name in ("temporalio", "sqlalchemy", "pydantic-ai-slim", "pytest")
                },
                "command": sys.argv,
                "samples": session.config.getoption("--ablation-samples"),
                "exit_status": int(exitstatus),
                "outcomes": OUTCOMES,
                "measurements": ROWS,
                "source_drift": drift,
                "sha256": SOURCE_MANIFEST,
            },
            indent=2,
        )
        + "\n"
    )

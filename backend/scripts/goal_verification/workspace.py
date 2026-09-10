"""Own source snapshots and same-session, same-source native evidence caches."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_identity() -> tuple[str, list[dict]]:
    def git(*args):
        return subprocess.check_output(["git", "-C", str(ROOT), *args])

    names = sorted(
        set(
            git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
        )
        - {""}
    )
    fingerprint = hashlib.sha256(git("rev-parse", "HEAD") + git("ls-files", "--stage", "-z"))
    entries = []
    for name in names:
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("Unsafe source path")
        if rel.parts[0] in {".steward", ".git"}:
            continue
        p = ROOT / rel
        if not p.exists() and not p.is_symlink():
            fingerprint.update(name.encode() + b"\0deleted\0")
            continue
        mode = stat.S_IMODE(p.lstat().st_mode)
        if p.is_symlink():
            value = os.readlink(p)
            if Path(value).is_absolute() or not p.resolve().is_relative_to(ROOT):
                raise ValueError("Source contains an external symlink: " + name)
            content = value.encode()
            kind = "symlink"
        else:
            content = p.read_bytes()
            kind = "file"
        item = {"path": name, "mode": mode, "kind": kind, "sha256": sha(content)}
        entries.append(item)
        fingerprint.update(json.dumps(item, sort_keys=True).encode())
    return fingerprint.hexdigest(), entries


def session_path(session: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", session):
        raise ValueError("Invalid verification session")
    return ROOT / ".steward" / "controls" / session


def environment(session: str, workspace: Path) -> dict[str, str]:
    config = json.loads((session_path(session) / "config.json").read_text())
    allowed = {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
    }
    env = {k: v for k, v in os.environ.items() if k in allowed}
    env.update(
        {
            "TEST_DATABASE_URL": config["testDatabaseUrl"],
            "DATABASE_URL": config["testDatabaseUrl"],
            "UV_PROJECT_ENVIRONMENT": config["pythonEnvironment"],
            "TEMPORAL_CLI": config["temporalCli"],
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "LOGFIRE_TOKEN": "",
            "LOGFIRE_API_KEY": "",
            "LOGFIRE_SEND_TO_LOGFIRE": "false",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "",
            "SIGNALDECK_API_TOKEN": "",
            "PLAYWRIGHT_HTML_OPEN": "never",
            "CLOSED_LOOP_SOURCE_ROOT": str(ROOT),
        }
    )
    env["PATH"] = str(Path(config["pythonEnvironment"]) / "bin") + os.pathsep + env.get("PATH", "")
    return env


def snapshot(session: str, identity: str, entries: list[dict]) -> tuple[Path, Path]:
    cache = session_path(session) / "sources" / identity
    cache.mkdir(parents=True, exist_ok=True)
    pointer = cache / "workspace.json"
    if pointer.exists():
        data = json.loads(pointer.read_text())
        workspace = Path(data["workspace"])
        if not workspace.is_dir():
            raise RuntimeError("Owned source snapshot is no longer present")
        return workspace, cache
    workspace = Path(tempfile.mkdtemp(prefix="signaldeck-goal-native-"))
    for item in entries:
        src, dest = ROOT / item["path"], workspace / item["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if item["kind"] == "symlink":
            dest.symlink_to(os.readlink(src))
        else:
            payload = src.read_bytes()
            if sha(payload) != item["sha256"]:
                raise RuntimeError("Source changed during snapshot: " + item["path"])
            dest.write_bytes(payload)
            dest.chmod(item["mode"])
    if source_identity()[0] != identity:
        raise RuntimeError("Source changed during snapshot")
    (workspace / "frontend/node_modules").symlink_to(
        ROOT / "frontend/node_modules", target_is_directory=True
    )
    env = environment(session, workspace)
    # uv is invoked without a shell; neither the invocation nor its log includes credentials.
    with (cache / "environment-setup.log").open("wb") as output:
        result = subprocess.run(
            ["uv", "sync", "--frozen", "--python", "3.13.13"],
            cwd=workspace / "backend",
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=300,
        )
    if result.returncode:
        raise RuntimeError("Locked verification environment setup failed")
    pointer.write_text(
        json.dumps({"workspace": str(workspace), "source": identity, "files": entries}, indent=2)
        + "\n"
    )
    return workspace, cache


def group_result(session: str, identity: str, entries: list[dict], group: str) -> tuple[dict, Path]:
    workspace, cache = snapshot(session, identity, entries)
    output = cache / "groups" / group
    seal = cache / "groups" / (group + ".manifest.json")
    if seal.exists():
        data = json.loads(seal.read_text())
        for name, expected in data["artifacts"].items():
            if sha((output / name).read_bytes()) != expected:
                raise RuntimeError("Cached native evidence changed: " + name)
        return data["result"], output
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("Interrupted group requires execution/environment recovery: " + group)
    output.parent.mkdir(parents=True, exist_ok=True)
    env = environment(session, workspace)
    if group == "real":
        from goal_verification.real import run_group

        result = run_group(workspace, output, env)
    else:
        from goal_verification.native import run_group

        result = run_group(group, workspace, output, env)
    if source_identity()[0] != identity:
        raise RuntimeError("Protected source changed while native group ran")
    hashes = {
        p.relative_to(output).as_posix(): sha(p.read_bytes())
        for p in output.rglob("*")
        if p.is_file()
    }
    seal.write_text(
        json.dumps(
            {"source": identity, "result": result, "artifacts": hashes},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return result, output

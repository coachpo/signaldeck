#!/usr/bin/env python3
"""Collect a read-only, secret-safe snapshot of the SignalDeck repository and deployment."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS_ROOT / "signaldeck-backup-restore" / "scripts"))
from signaldeck_ops_common import (  # noqa: E402
    REMOTE_COMMON,
    OpsError,
    redact,
    ssh_python,
    validate_project,
)

REMOTE_SNAPSHOT = (
    REMOTE_COMMON
    + r'''
def published_ports(info):
    ports = []
    for container_port, bindings in sorted((info.get("NetworkSettings", {}).get("Ports") or {}).items()):
        for binding in bindings or []:
            ports.append(f"{binding.get('HostIp')}:{binding.get('HostPort')}->{container_port}")
    return ports


def volume_sizes(topology):
    names = run([
        "docker", "volume", "ls", "-q",
        "--filter", f"label=com.docker.compose.project={topology['project']}",
    ]).split()
    image = inspect(container_id(topology, "db"))["Image"]
    sizes = {}
    for name in sorted(names):
        raw = run([
            "docker", "run", "--rm", "--network", "none", "--entrypoint", "du",
            "-v", f"{name}:/source:ro", image, "-sk", "/source",
        ])
        sizes[name] = int(raw.split()[0]) * 1024
    return sizes


def backup_inventory(topology):
    root = topology["backup_root"] / topology["project"]
    items = []
    if not root.is_dir():
        return items
    for child in sorted(root.iterdir()):
        entry = {"name": child.name}
        try:
            manifest = validate_backup(child, topology["project"], verify_hashes=False)
            entry.update(
                status="verified",
                created_at=manifest.get("created_at"),
                app_image_ref=manifest.get("app_image_ref"),
                bytes=sum(item["size_bytes"] for item in manifest["artifacts"].values()),
            )
        except ValueError as exc:
            entry.update(status="unmanaged_or_incomplete", reason=str(exc))
        items.append(entry)
    return items


def deploy_repository(topology):
    root = str(topology["deploy_root"])
    head = run(["git", "-C", root, "rev-parse", "HEAD"], check=False)
    dirty = run(
        ["git", "-C", root, "status", "--porcelain", "--", topology["deploy_name"]], check=False
    )
    return {"head": head or None, "dirty_paths": [line[3:] for line in dirty.splitlines() if line]}


def snapshot_main():
    args = payload()
    topology = discover(args["project"], args.get("backup_root"))
    services = {}
    for name, infos in sorted(project_containers(topology["project"]).items()):
        entries = []
        for info in infos:
            labels = image_labels(info["Image"])
            try:
                immutable = immutable_image_ref(info)
            except RuntimeError:
                immutable = None
            entries.append({
                **safe_state(info),
                "immutable_image_ref": immutable,
                "oci_revision": labels.get("org.opencontainers.image.revision"),
                "oci_version": labels.get("org.opencontainers.image.version"),
                "published_ports": published_ports(info),
            })
        services[name] = entries
    health_status, health_body = app_http(topology, "/health")
    ready_status, ready_body = app_http(topology, "/ready")
    pins = env_pins(topology)
    pinned = pins.get(topology["version_var"])
    result = {
        "observed_at": utc_now().isoformat(),
        "topology": public_topology(topology),
        "services": services,
        "http": {
            "health": {"status": health_status, "body": json.loads(health_body) if health_status == 200 else None},
            "ready": {"status": ready_status, "body": json.loads(ready_body) if ready_status in (200, 503) else None},
        },
        "env_pins": pins,
        "pinned_app_image": f"{topology['app_repository']}:{pinned}" if pinned else None,
        "postgres_version": psql(topology, "SHOW server_version"),
        "databases": databases(topology),
        "counts": application_counts(topology),
        "volumes": volume_sizes(topology),
        "backups": backup_inventory(topology),
        "backup_free_bytes": shutil.disk_usage(
            topology["backup_root"] if topology["backup_root"].exists() else topology["deploy_root"]
        ).free,
        "deploy_repository": deploy_repository(topology),
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        snapshot_main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
'''
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def git_value(repo: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def parse_origin_slug(origin: str | None) -> str | None:
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", origin or "")
    return f"{match.group(1)}/{match.group(2)}" if match else None


def version_surfaces(repo: Path) -> dict[str, str | None]:
    def text(path: Path) -> str | None:
        return path.read_text(encoding="utf-8").strip() if path.is_file() else None

    pyproject = text(repo / "backend" / "pyproject.toml") or ""
    project = re.search(r"(?ms)^\[project\]\s*$(.*?)(?=^\[|\Z)", pyproject)
    name = re.search(r'(?m)^name\s*=\s*"([^"]+)"', project.group(1)) if project else None
    version = re.search(r'(?m)^version\s*=\s*"([^"]+)"', project.group(1)) if project else None
    lock = text(repo / "backend" / "uv.lock") or ""
    locked = (
        re.search(
            r'(?m)^\[\[package\]\]\nname = "' + re.escape(name.group(1)) + r'"\nversion = "([^"]+)"',
            lock,
        )
        if name
        else None
    )
    package = repo / "frontend" / "package.json"
    return {
        "VERSION": text(repo / "VERSION"),
        "backend/VERSION": text(repo / "backend" / "VERSION"),
        "backend/pyproject.toml": version.group(1) if version else None,
        "backend/uv.lock": locked.group(1) if locked else None,
        "frontend/VERSION": text(repo / "frontend" / "VERSION"),
        "frontend/package.json": (
            str(json.loads(package.read_text(encoding="utf-8")).get("version"))
            if package.is_file()
            else None
        ),
    }


def github_runs(slug: str, head: str) -> list[dict[str, object]]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{slug}/actions/runs?head_sha={head}&per_page=20",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "signaldeck-ops"},
    )
    token = os.getenv("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    return [
        {
            "name": item.get("name"),
            "event": item.get("event"),
            "head_branch": item.get("head_branch"),
            "status": item.get("status"),
            "conclusion": item.get("conclusion"),
            "url": item.get("html_url"),
        }
        for item in payload.get("workflow_runs", [])
    ]


def repository_snapshot(repo: Path) -> tuple[dict[str, object], list[str]]:
    limitations: list[str] = []
    head = git_value(repo, "rev-parse", "HEAD")
    slug = parse_origin_slug(git_value(repo, "remote", "get-url", "origin"))
    result: dict[str, object] = {
        "root": str(repo),
        "head": head,
        "branch": git_value(repo, "branch", "--show-current"),
        "dirty": bool(git_value(repo, "status", "--porcelain")),
        "origin": slug,
        "tags_at_head": (git_value(repo, "tag", "--points-at", "HEAD") or "").split(),
        "latest_release_tag": git_value(repo, "describe", "--tags", "--abbrev=0", "--match", "v*"),
        "version_surfaces": version_surfaces(repo),
    }
    if slug and head:
        try:
            result["workflow_runs"] = github_runs(slug, head)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            limitations.append(f"GitHub workflow runs unavailable: {type(exc).__name__}")
    return result, limitations


def check_snapshot(snapshot: dict[str, object]) -> list[str]:
    failures: list[str] = []
    repository = snapshot.get("repository") or {}
    surfaces = repository.get("version_surfaces") or {}
    if len(set(surfaces.values())) != 1 or None in surfaces.values():
        failures.append("repository version surfaces are not aligned")
    deployment = snapshot.get("deployment")
    if not isinstance(deployment, dict):
        failures.append("deployment snapshot unavailable")
        return failures
    services = deployment["services"]
    for name in ("app", "db", "temporal"):
        state = services[name][0]
        if state["status"] != "running" or state["health"] != "healthy":
            failures.append(f"{name} is {state['status']}/{state['health']}")
    for name in ("dispatcher", "worker"):
        if services[name][0]["status"] != "running":
            failures.append(f"{name} is {services[name][0]['status']}")
    roles = deployment["topology"]["app_roles"]
    role_refs = {entry["image_ref"] for name in roles for entry in services[name]}
    if len(role_refs) != 1:
        failures.append(f"application roles run different images: {sorted(role_refs)}")
    pinned = deployment.get("pinned_app_image")
    if pinned is not None and role_refs != {pinned}:
        failures.append(f"pinned application image {pinned} differs from the running image")
    if deployment["http"]["ready"]["status"] != 200:
        failures.append("the application /ready check is failing")
    for name, entries in services.items():
        for entry in entries:
            if entry["status"] == "restarting":
                failures.append(f"{name} is restarting")
            if entry["status"] == "exited" and entry["exit_code"] not in (0, None):
                failures.append(f"{name} exited with {entry['exit_code']}")
    return failures


def atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="capy", help="SSH deployment host")
    parser.add_argument("--project", default="signaldeck", help="Compose project name")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--backup-root", help="absolute remote backup root override")
    parser.add_argument("--output", type=Path, help="write the JSON snapshot atomically")
    parser.add_argument(
        "--check", action="store_true", help="exit 1 when an invariant check fails"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = validate_project(args.project)
    repository, limitations = repository_snapshot(args.repo_root.resolve())
    snapshot: dict[str, object] = {
        "schema_version": 1,
        "observed_at": utc_now(),
        "host": args.host,
        "repository": repository,
        "limitations": limitations,
    }
    try:
        snapshot["deployment"] = ssh_python(
            args.host,
            REMOTE_SNAPSHOT,
            {"project": project, "backup_root": args.backup_root},
            timeout=600,
        )
    except (OpsError, subprocess.TimeoutExpired) as exc:
        snapshot["deployment"] = None
        limitations.append(redact(f"deployment snapshot failed: {exc}"))
    snapshot["checks"] = check_snapshot(snapshot)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        atomic_write(args.output.resolve(), payload)
        print(json.dumps({"output": str(args.output.resolve()), "checks": snapshot["checks"]}))
    else:
        sys.stdout.write(payload)
    return 1 if args.check and snapshot["checks"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OpsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

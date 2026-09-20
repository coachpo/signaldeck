#!/usr/bin/env python3
"""Plan, execute or recover a SignalDeck release and write an immutable release manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from ssh_command import ssh_command


class ReleaseError(RuntimeError):
    pass


SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|token|secret|api[-_ ]?key|credential|authorization|cookie|database[_ .-]?url)"
)
# The single image of .github/workflows/docker-images.yml, which every
# application and plugin role runs, and its GHCR image name.
IMAGES = {"app": "signaldeck"}
WORKFLOWS = ("CI", "Docker Images")
SINGLE_MANIFEST_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}


def redact(value: str) -> str:
    return "\n".join(
        "<redacted secret-bearing line>" if SECRET_PATTERN.search(line) else line
        for line in value.splitlines()
    )


def run(argv: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = redact((result.stderr or result.stdout).strip())
        raise ReleaseError(f"command failed ({result.returncode}): {argv[0]}: {detail}")
    return result.stdout.strip()


def parse_release_plan(output: str) -> dict[str, str]:
    fields = {}
    patterns = {
        "current_version": r"^\s*Current version\s*:\s*(\S+)\s*$",
        "version": r"^\s*Target version\s*:\s*(\S+)\s*$",
        "tag": r"^\s*Root tag\s*:\s*(\S+)\s*$",
    }
    for name, pattern in patterns.items():
        match = re.search(pattern, output, re.MULTILINE)
        if not match:
            raise ReleaseError(f"release dry-run did not report {name}")
        fields[name] = match.group(1)
    if fields["tag"] != "v" + fields["version"]:
        raise ReleaseError("release tag/version mismatch")
    return fields


def parse_origin_slug(origin: str) -> str:
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", origin)
    if not match:
        raise ReleaseError("origin is not a supported GitHub repository")
    return f"{match.group(1)}/{match.group(2)}"


def github_json(url: str) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "signaldeck-release"},
    )
    token = os.getenv("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            value = json.load(response)
    except (OSError, urllib.error.HTTPError, ValueError) as exc:
        raise ReleaseError(f"GitHub API request failed: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ReleaseError("GitHub API returned a non-object")
    return value


def selected_workflows(
    payload: dict[str, object], *, release_sha: str, tag: str
) -> dict[str, dict[str, object]]:
    """The release commit's push CI on main and the tag's image workflow, newest first."""
    selected: dict[str, dict[str, object]] = {}
    for item in payload.get("workflow_runs", []):
        name = item.get("name")
        if name not in WORKFLOWS or name in selected:
            continue
        expected_branch = "main" if name == "CI" else tag
        if (
            item.get("event") != "push"
            or item.get("head_sha") != release_sha
            or item.get("head_branch") != expected_branch
        ):
            continue
        selected[name] = {
            "name": name,
            "id": item.get("id"),
            "status": item.get("status"),
            "conclusion": item.get("conclusion"),
            "url": item.get("html_url"),
            "event": item.get("event"),
            "head_sha": item.get("head_sha"),
            "head_branch": item.get("head_branch"),
        }
    return selected


def workflow_gate(workflows: dict[str, dict[str, object]]) -> str:
    for item in workflows.values():
        if item["status"] == "completed" and item["conclusion"] != "success":
            return "failed"
    if set(workflows) == set(WORKFLOWS) and all(
        item["status"] == "completed" and item["conclusion"] == "success"
        for item in workflows.values()
    ):
        return "success"
    return "pending"


def wait_workflows(
    slug: str, release_sha: str, tag: str, timeout: int, poll: int
) -> dict[str, dict[str, object]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = github_json(
            f"https://api.github.com/repos/{slug}/actions/runs?head_sha={release_sha}&per_page=30"
        )
        workflows = selected_workflows(payload, release_sha=release_sha, tag=tag)
        gate = workflow_gate(workflows)
        if gate == "success":
            return workflows
        if gate == "failed":
            raise ReleaseError(f"release workflow failed: {json.dumps(workflows, sort_keys=True)}")
        time.sleep(poll)
    raise ReleaseError("timed out waiting for release workflows")


def inspect_image(host: str, image_ref: str) -> dict[str, object]:
    manifest_raw = run(
        ssh_command(
            host,
            ["docker", "buildx", "imagetools", "inspect", image_ref, "--format", "{{json .Manifest}}"],
        )
    )
    image_raw = run(
        ssh_command(
            host,
            ["docker", "buildx", "imagetools", "inspect", image_ref, "--format", "{{json .Image}}"],
        )
    )
    try:
        manifest = json.loads(manifest_raw)
        image = json.loads(image_raw)
    except ValueError as exc:
        raise ReleaseError("image inspection returned invalid JSON") from exc
    labels = (image.get("config") or {}).get("Labels") or {}
    return {
        "manifest_digest": manifest.get("digest"),
        "manifest_media_type": manifest.get("mediaType"),
        "os": image.get("os"),
        "architecture": image.get("architecture"),
        "revision": labels.get("org.opencontainers.image.revision"),
        "version": labels.get("org.opencontainers.image.version"),
    }


def normalized_host_arch(value: str) -> str:
    return {"aarch64": "arm64", "x86_64": "amd64"}.get(value.strip(), value.strip())


def validate_published_image(
    inspected: dict[str, object], *, release_sha: str, version: str, host_arch: str
) -> None:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(inspected.get("manifest_digest"))):
        raise ReleaseError("published image has no manifest digest")
    if inspected.get("manifest_media_type") not in SINGLE_MANIFEST_TYPES:
        raise ReleaseError("published image is not a single-platform manifest")
    if inspected.get("revision") != release_sha or inspected.get("version") != version:
        raise ReleaseError("OCI revision/version does not match the release")
    if inspected.get("os") != "linux" or inspected.get("architecture") != host_arch:
        raise ReleaseError("published image platform does not match the deployment host")


def version_surfaces(repo: Path) -> dict[str, str]:
    pyproject = (repo / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    project = re.search(r"(?ms)^\[project\]\s*$(.*?)(?=^\[|\Z)", pyproject)
    if not project:
        raise ReleaseError("backend/pyproject.toml has no [project] table")
    name = re.search(r'(?m)^name\s*=\s*"([^"]+)"', project.group(1))
    version = re.search(r'(?m)^version\s*=\s*"([^"]+)"', project.group(1))
    if not name or not version:
        raise ReleaseError("backend/pyproject.toml lacks a project name or version")
    locked = re.findall(
        r'(?m)^\[\[package\]\]\nname = "' + re.escape(name.group(1)) + r'"\nversion = "([^"]+)"',
        (repo / "backend" / "uv.lock").read_text(encoding="utf-8"),
    )
    if len(locked) != 1:
        raise ReleaseError("backend/uv.lock does not lock the project exactly once")
    package = json.loads((repo / "frontend" / "package.json").read_text(encoding="utf-8"))
    return {
        "VERSION": (repo / "VERSION").read_text(encoding="utf-8").strip(),
        "backend/VERSION": (repo / "backend" / "VERSION").read_text(encoding="utf-8").strip(),
        "backend/pyproject.toml": version.group(1),
        "backend/uv.lock": locked[0],
        "frontend/VERSION": (repo / "frontend" / "VERSION").read_text(encoding="utf-8").strip(),
        "frontend/package.json": str(package["version"]),
    }


def write_new(path: Path, value: dict[str, object]) -> None:
    if path.exists():
        raise ReleaseError(f"refusing to overwrite release manifest: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def release_plan(repo: Path, spec: str) -> dict[str, object]:
    helper = repo / "release.sh"
    if not helper.is_file():
        raise ReleaseError("release.sh not found")
    plan: dict[str, object] = dict(parse_release_plan(run([str(helper), spec, "--dry-run"], cwd=repo)))
    plan.update(
        {
            "action": "plan",
            "repo_root": str(repo),
            "head": run(["git", "rev-parse", "HEAD"], cwd=repo),
            "branch": run(["git", "branch", "--show-current"], cwd=repo),
            "dirty": bool(run(["git", "status", "--porcelain"], cwd=repo)),
        }
    )
    return plan


def require_current_main(repo: Path) -> str:
    head = run(["git", "rev-parse", "HEAD"], cwd=repo)
    if run(["git", "status", "--porcelain"], cwd=repo) or run(
        ["git", "branch", "--show-current"], cwd=repo
    ) != "main":
        raise ReleaseError("release requires a clean main branch")
    run(["git", "fetch", "origin", "main", "--tags"], cwd=repo)
    upstream = run(["git", "rev-parse", "origin/main"], cwd=repo)
    remote_main = run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=repo).split()[0]
    if len({head, upstream, remote_main}) != 1:
        raise ReleaseError("local main, origin/main and remote main are not identical")
    return head


def recovery_plan(repo: Path, spec: str) -> dict[str, object]:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", spec):
        raise ReleaseError("release recovery requires an exact X.Y.Z version")
    tag = "v" + spec
    head = require_current_main(repo)
    local_tag = run(["git", "rev-list", "-n1", tag], cwd=repo)
    remote_tag_raw = run(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"], cwd=repo)
    if not remote_tag_raw or remote_tag_raw.split()[0] != local_tag:
        raise ReleaseError("release recovery requires identical local and remote tags")
    run(["git", "merge-base", "--is-ancestor", local_tag, head], cwd=repo)
    if set(version_surfaces(repo).values()) != {spec}:
        raise ReleaseError("release recovery version surfaces are not aligned")
    return {"action": "recover", "version": spec, "tag": tag, "head": head, "release_sha": local_tag}


def finalize_manifest(
    repo: Path,
    *,
    release_spec: str,
    version: str,
    tag: str,
    release_sha: str,
    host: str,
    timeout_seconds: int,
    poll_seconds: int,
) -> dict[str, object]:
    slug = parse_origin_slug(run(["git", "remote", "get-url", "origin"], cwd=repo))
    workflows = wait_workflows(slug, release_sha, tag, timeout_seconds, poll_seconds)
    host_arch = normalized_host_arch(run(ssh_command(host, ["uname", "-m"])))
    owner = slug.split("/", 1)[0].lower()
    images: dict[str, object] = {}
    for service, name in IMAGES.items():
        repository = f"ghcr.io/{owner}/{name}"
        inspected = inspect_image(host, f"{repository}:{tag}")
        validate_published_image(
            inspected, release_sha=release_sha, version=version, host_arch=host_arch
        )
        images[service] = {
            "repository": repository,
            "ref": f"{repository}:{tag}@{inspected['manifest_digest']}",
            **inspected,
        }
    surfaces = version_surfaces(repo)
    if set(surfaces.values()) != {version}:
        raise ReleaseError("release version surfaces are not aligned")
    return {
        "schema_version": 1,
        "status": "published",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": slug,
        "release_spec": release_spec,
        "version": version,
        "tag": tag,
        "release_sha": release_sha,
        "commit_subject": run(["git", "log", "-1", "--pretty=%s", release_sha], cwd=repo),
        "version_surfaces": surfaces,
        "workflows": workflows,
        "images": images,
    }


def default_manifest_path(repo: Path, tag: str) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return repo / "artifacts" / "evidence" / "signaldeck-ops" / "releases" / f"{stamp}-{tag}.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="action", required=True)
    for action in ("plan", "execute", "recover"):
        command = subparsers.add_parser(action)
        command.add_argument("--repo-root", type=Path, default=Path.cwd())
        command.add_argument("--spec", required=True)
        command.add_argument("--host", default="capy", help="host used for OCI inspection")
        command.add_argument("--manifest", type=Path)
        command.add_argument("--confirm-release")
        command.add_argument("--timeout-seconds", type=int, default=3600)
        command.add_argument("--poll-seconds", type=int, default=30)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repo = args.repo_root.resolve()
    if args.action == "recover":
        plan = recovery_plan(repo, args.spec)
        if args.confirm_release != plan["tag"]:
            raise ReleaseError(f"recover requires --confirm-release {plan['tag']}")
        release_sha = str(plan["release_sha"])
    else:
        plan = release_plan(repo, args.spec)
        if args.action == "plan":
            print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.confirm_release != plan["tag"]:
            raise ReleaseError(f"execute requires --confirm-release {plan['tag']}")
        require_current_main(repo)
        if run(["git", "tag", "-l", str(plan["tag"])], cwd=repo) or run(
            ["git", "ls-remote", "--tags", "origin", f"refs/tags/{plan['tag']}"], cwd=repo
        ):
            raise ReleaseError("release tag already exists")
        run([str(repo / "release.sh"), args.spec, "--yes"], cwd=repo)
        release_sha = run(["git", "rev-parse", "HEAD"], cwd=repo)
        if run(["git", "rev-list", "-n1", str(plan["tag"])], cwd=repo) != release_sha:
            raise ReleaseError("release tag does not point to release HEAD")
        if run(["git", "status", "--porcelain"], cwd=repo):
            raise ReleaseError("release helper left a dirty worktree")
    manifest = finalize_manifest(
        repo,
        release_spec=args.spec,
        version=str(plan["version"]),
        tag=str(plan["tag"]),
        release_sha=release_sha,
        host=args.host,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    manifest_path = (args.manifest or default_manifest_path(repo, str(plan["tag"]))).resolve()
    write_new(manifest_path, manifest)
    print(
        json.dumps(
            {"manifest": str(manifest_path), **manifest}, ensure_ascii=False, indent=2, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

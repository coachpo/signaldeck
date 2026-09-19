#!/usr/bin/env python3
"""Plan or execute a gated SignalDeck application rollout from a published release manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

from signaldeck_release import (
    IMAGES,
    ReleaseError,
    inspect_image,
    normalized_host_arch,
    validate_published_image,
)
from ssh_command import ssh_command

SKILLS_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SCRIPTS = SKILLS_ROOT / "signaldeck-backup-restore" / "scripts"
sys.path.insert(0, str(BACKUP_SCRIPTS))
from signaldeck_ops_common import (  # noqa: E402
    REMOTE_COMMON,
    OpsError,
    redact,
    ssh_python,
    validate_project,
)


class RolloutError(RuntimeError):
    pass


# Read-only list endpoints that only project stored records.
SMOKE_PATHS = (
    "/api/workflow-packages",
    "/api/runs",
    "/api/schedules",
    "/api/plugins",
    "/api/plugin-pages",
    "/api/resources",
    "/api/task-presets",
)

REMOTE_ROLLOUT_HELPERS = r'''
import stat
from urllib.parse import urlsplit

LONG_RUNNING = frozenset({"always", "unless-stopped", "on-failure"})


def version_spec(image_ref, repository):
    if not image_ref.startswith(repository + ":"):
        raise RuntimeError("release image is not in the deployed application repository")
    return image_ref[len(repository) + 1:]


def long_running(info):
    return (info.get("HostConfig", {}).get("RestartPolicy") or {}).get("Name") in LONG_RUNNING


def require_service_state(name, info):
    state = safe_state(info)
    if long_running(info):
        healthy = state["health"] in (None, "healthy")
        if state["status"] != "running" or not healthy:
            raise RuntimeError(f"{name} is {state['status']}/{state['health']}")
    elif state["status"] != "exited" or state["exit_code"] != 0:
        raise RuntimeError(f"one-shot {name} is {state['status']} with exit {state['exit_code']}")
    return state


def wait_one_shots(topology, names, deadline_seconds=300):
    deadline = time.monotonic() + deadline_seconds
    while True:
        containers = project_containers(topology["project"])
        pending = [
            name
            for name in names
            if not long_running(containers[name][0])
            and safe_state(containers[name][0])["status"] in ("created", "running", "restarting")
        ]
        if not pending:
            return containers
        if time.monotonic() > deadline:
            raise RuntimeError(f"one-shot services did not finish: {pending}")
        time.sleep(5)


def schema_report_from(raw):
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("schema compatibility check produced no report")
    report = json.loads(lines[-1])
    return {
        "compatible": report["compatible"],
        "tables": {name: item["status"] for name, item in report["tables"].items()},
        "incompatible": {
            name: item for name, item in report["tables"].items() if item["status"] == "incompatible"
        },
        "unknown_tables": report["unknown_tables"],
    }
'''

REMOTE_PREFLIGHT = (
    REMOTE_COMMON
    + REMOTE_ROLLOUT_HELPERS
    + r'''
def preflight_main():
    args = payload()
    topology = discover(args["project"], args.get("backup_root"))
    if topology["app_repository"] != args["app_repository"]:
        raise RuntimeError("the deployment runs another application image repository")
    containers = project_containers(topology["project"])
    for name in ("app", "dispatcher", "worker", "db", "temporal"):
        require_service_state(name, containers[name][0])
    print(json.dumps({
        "topology": public_topology(topology),
        "previous_app_image": immutable_image_ref(containers["app"][0]),
        "service_images": {
            name: infos[0]["Config"]["Image"]
            for name, infos in sorted(containers.items())
            if name not in topology["app_roles"] and len(infos) == 1
        },
        "env_pins": env_pins(topology),
        "health": wait_app_ready(topology, deadline_seconds=60),
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        preflight_main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
'''
)

REMOTE_SCHEMA_CHECK = (
    REMOTE_COMMON
    + REMOTE_ROLLOUT_HELPERS
    + r'''
def schema_check_main():
    args = payload()
    topology = discover(args["project"], args.get("backup_root"))
    run(["docker", "pull", "--quiet", args["image_ref"]])
    environment = os.environ.copy()
    environment[topology["version_var"]] = version_spec(args["image_ref"], topology["app_repository"])
    # Run the new image's own model check against the live database without switching.
    result = subprocess.run(
        compose_argv(
            topology, "run", "--rm", "--no-deps", "-T", "--entrypoint", "python",
            "app", "-m", "app.infrastructure.schema_compatibility",
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"schema check failed ({result.returncode}): {redacted_tail(result.stderr)}")
    print(json.dumps(schema_report_from(result.stdout.decode("utf-8", "replace")), sort_keys=True))


if __name__ == "__main__":
    try:
        schema_check_main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
'''
)

REMOTE_PLUGIN_COMPARE = (
    REMOTE_COMMON
    + REMOTE_ROLLOUT_HELPERS
    + r'''
import tempfile

APPLICATION = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*")
# Mirrors plugin_runtime.describe, but also accepts a module-level application and
# prints only the release identity.
DESCRIBE = """
import asyncio, json, sys
from importlib import import_module
module, attribute = sys.argv[1].split(":", 1)
app = getattr(import_module(module), attribute)
if sys.argv[2] == "factory":
    app = app()
for route in app.routes:
    if getattr(route, "path", None) == "/release":
        value = route.endpoint()
        if asyncio.iscoroutine(value):
            value = asyncio.run(value)
        print(json.dumps({"releaseId": value.get("releaseId"), "artifactDigest": value.get("artifactDigest")}))
        break
else:
    raise SystemExit("plugin exposes no release descriptor")
"""


def descriptor_identity(raw):
    value = json.loads(raw)
    return {"releaseId": value.get("releaseId"), "artifactDigest": value.get("artifactDigest")}


def plugin_application(image_ref):
    command = json.loads(run(["docker", "image", "inspect", image_ref, "--format", "{{json .Config.Cmd}}"])) or []
    matches = [item for item in command if APPLICATION.fullmatch(item)]
    if len(matches) != 1:
        raise RuntimeError("plugin image command names no single application")
    return matches[0], "factory" if "--factory" in command else "app"


def service_environment(info):
    """The container's own environment minus the values its image defines."""
    image = json.loads(run(["docker", "image", "inspect", info["Image"]]))[0]
    defaults = set(image.get("Config", {}).get("Env") or [])
    return [item for item in info.get("Config", {}).get("Env") or [] if item not in defaults]


def compare_plugin(info, new_ref):
    probe = json.loads(run([
        "docker", "exec", info["Id"], "python", "-c", HTTP_PROBE, "/release", "10", "8000",
    ]))
    if probe["status"] != 200:
        raise RuntimeError(f"running descriptor returned HTTP {probe['status']}")
    current = descriptor_identity(probe["body"])
    run(["docker", "pull", "--quiet", new_ref])
    application, kind = plugin_application(new_ref)
    # The descriptor digest covers the service configuration, so describe the new image
    # with the running service's environment, passed through a private file and no network.
    directory = tempfile.mkdtemp(prefix="signaldeck-describe-")
    try:
        env_file = Path(directory) / "service.env"
        env_file.write_text("".join(item + "\n" for item in service_environment(info)), encoding="utf-8")
        os.chmod(env_file, 0o600)
        described = subprocess.run(
            [
                "docker", "run", "--rm", "--network", "none", "--env-file", str(env_file),
                "--entrypoint", "python", new_ref, "-c", DESCRIBE, application, kind,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    # Tracebacks may echo configuration values, so only the exit status is reported.
    if described.returncode != 0:
        raise RuntimeError(f"describing the new image failed ({described.returncode})")
    new = descriptor_identity(described.stdout.decode("utf-8", "replace").splitlines()[-1])
    return {
        "current_image": info["Config"]["Image"],
        "new_image": new_ref,
        "current": current,
        "new": new,
        "changed": current["artifactDigest"] != new["artifactDigest"],
    }


def plugin_compare_main():
    args = payload()
    topology = discover(args["project"], args.get("backup_root"))
    defaults = topology["service_dir"] / "plugin-defaults.json"
    entries = json.loads(defaults.read_text(encoding="utf-8")) if defaults.is_file() else []
    containers = project_containers(topology["project"])
    results = {}
    for entry in entries:
        profile = entry.get("profile")
        service = urlsplit(entry.get("descriptorUrl") or "").hostname
        new_ref = args["images"].get(profile)
        infos = containers.get(service, [])
        if new_ref is None or len(infos) != 1:
            results[profile] = {"service": service, "status": "unknown", "reason": "no single current service"}
            continue
        try:
            results[profile] = {"service": service, "status": "compared", **compare_plugin(infos[0], new_ref)}
        except (RuntimeError, ValueError, KeyError) as exc:
            results[profile] = {"service": service, "status": "unknown", "reason": str(exc)}
    print(json.dumps({"plugins": results}, sort_keys=True))


if __name__ == "__main__":
    try:
        plugin_compare_main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
'''
)

REMOTE_READ_BACKUP = (
    REMOTE_COMMON
    + r'''
if __name__ == "__main__":
    try:
        args = payload()
        manifest = validate_backup(Path(args["manifest"]).parent, args["project"], verify_hashes=False)
        print(json.dumps({
            "created_at": manifest["created_at"],
            "app_image_ref": manifest["app_image_ref"],
            "counts": manifest["counts"],
            "evidence_consistency": manifest["evidence_consistency"],
        }, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
'''
)

REMOTE_POST_DEPLOY = (
    REMOTE_COMMON
    + REMOTE_ROLLOUT_HELPERS
    + r'''
def post_deploy_main():
    args = payload()
    topology = discover(args["project"], args.get("backup_root"))
    health = wait_app_ready(topology, expected_version=args["version"])
    containers = wait_one_shots(topology, list(project_containers(topology["project"])))
    roles = {}
    for name in topology["app_roles"]:
        info = containers[name][0]
        if info["Config"]["Image"] != args["image_ref"]:
            raise RuntimeError(f"{name} does not run the release image")
        roles[name] = require_service_state(name, info)
    others = {}
    for name, image in sorted(args["service_images"].items()):
        infos = containers.get(name, [])
        if len(infos) != 1 or infos[0]["Config"]["Image"] != image:
            raise RuntimeError(f"{name} changed during an application-only rollout")
        others[name] = require_service_state(name, infos[0])
    counts = application_counts(topology)
    regressions = count_regressions(args["backup_counts"], counts)
    if regressions:
        raise RuntimeError(f"durable row counts decreased: {regressions}")
    schema = schema_report_from(run([
        "docker", "exec", container_id(topology, "app"),
        "python", "-m", "app.infrastructure.schema_compatibility",
    ], check=False))
    if not schema["compatible"] or set(schema["tables"].values()) != {"ok"}:
        raise RuntimeError(f"live schema does not match the release models: {schema}")
    smoke = {}
    for path in args["smoke_paths"]:
        smoke[path] = app_http(topology, path)[0]
    status, body = app_http(topology, "/api/plugin-pages")
    for page in json.loads(body) if status == 200 else []:
        path = f"/_plugins/{page['mountKey']}/"
        smoke[path] = app_http(topology, path)[0]
    failed = {path: code for path, code in smoke.items() if code != 200}
    if failed:
        raise RuntimeError(f"read-only smoke failed: {failed}")
    print(json.dumps({
        "health": health,
        "app_roles": roles,
        "other_services": others,
        "counts": counts,
        "schema": schema,
        "smoke": smoke,
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        post_deploy_main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
'''
)

REMOTE_PIN = (
    REMOTE_COMMON
    + REMOTE_ROLLOUT_HELPERS
    + r'''
def pin_main():
    args = payload()
    topology = discover(args["project"], args.get("backup_root"))
    env_file = topology["env_file"]
    if env_file is None:
        raise RuntimeError("the deployment has no env file to pin the release in")
    spec = version_spec(args["image_ref"], topology["app_repository"])
    original = env_file.read_text(encoding="utf-8")
    before = file_sha(env_file)
    mode = stat.S_IMODE(env_file.stat().st_mode)

    def install(content):
        temporary = env_file.with_name(f".{env_file.name}.{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.chmod(temporary, mode)
        os.replace(temporary, env_file)

    install(replace_env_value(original, topology["version_var"], spec))
    # Render without any shell override, so only the persisted source decides the image.
    environment = {key: value for key, value in os.environ.items() if key != topology["version_var"]}
    rendered = json.loads(run(compose_argv(topology, "config", "--format", "json"), env=environment))
    images = {
        name: service.get("image")
        for name, service in rendered.get("services", {}).items()
        if name in topology["app_roles"]
    }
    if not images or set(images.values()) != {args["image_ref"]}:
        install(original)
        raise RuntimeError(f"rendered application images differ from the release: {images}")
    print(json.dumps({
        "env_file": str(env_file),
        "variable": topology["version_var"],
        "value": spec,
        "sha256_before": before,
        "sha256_after": file_sha(env_file),
        "rendered_images": images,
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        pin_main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
'''
)

REMOTE_OBSERVE = (
    REMOTE_COMMON
    + REMOTE_ROLLOUT_HELPERS
    + r'''
def observe_main():
    args = payload()
    topology = discover(args["project"], args.get("backup_root"))
    names = ("app", "dispatcher", "worker", "db", "temporal")
    baseline = {name: service_state(topology, name) for name in names}
    started = time.monotonic()
    deadline = started + args["seconds"]
    samples = 0
    while True:
        for name in names:
            state = service_state(topology, name)
            first = baseline[name]
            if state["container"] != first["container"] or state["restarts"] != first["restarts"]:
                raise RuntimeError(f"{name} restarted or was replaced during observation")
            if state["status"] != "running" or state["health"] not in (None, "healthy"):
                raise RuntimeError(f"{name} became {state['status']}/{state['health']}")
            if name in ("app", "dispatcher", "worker") and state["image_ref"] != args["image_ref"]:
                raise RuntimeError(f"{name} image changed during observation")
        ready, _ = app_http(topology, "/ready")
        status, body = app_http(topology, "/health")
        health = json.loads(body) if status == 200 else {}
        if ready != 200 or health.get("version") != args["version"]:
            raise RuntimeError(f"health check failed during observation: ready={ready} health={health}")
        samples += 1
        if time.monotonic() >= deadline:
            break
        time.sleep(min(10, max(0, deadline - time.monotonic())))
    print(json.dumps({
        "status": "stable",
        "samples": samples,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "restarts": {name: state["restarts"] for name, state in baseline.items()},
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        observe_main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
'''
)

REMOTE_STOP = (
    REMOTE_COMMON
    + r'''
if __name__ == "__main__":
    try:
        args = payload()
        topology = discover(args["project"], args.get("backup_root"))
        stop_services(topology, ("app", "dispatcher", "worker"))
        print(json.dumps({"status": "stopped", "services": ["app", "dispatcher", "worker"]}))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
'''
)


def load_manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RolloutError(f"cannot read release manifest: {path}") from exc
    if value.get("schema_version") != 1 or value.get("status") != "published":
        raise RolloutError("rollout requires a published schema-version-1 manifest")
    slug = str(value.get("repository", ""))
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", slug) or ".." in slug.split("/"):
        raise RolloutError("release manifest has an invalid repository slug")
    if not re.fullmatch(r"[0-9a-f]{40}", str(value.get("release_sha", ""))):
        raise RolloutError("release manifest has no full release SHA")
    if value.get("tag") != f"v{value.get('version')}":
        raise RolloutError("release manifest tag and version differ")
    images = value.get("images")
    if not isinstance(images, dict) or set(images) != set(IMAGES):
        raise RolloutError("release manifest must list exactly the published images")
    owner = slug.split("/", 1)[0].lower()
    for service, name in IMAGES.items():
        image = images[service]
        repository = f"ghcr.io/{owner}/{name}"
        digest = str(image.get("manifest_digest", ""))
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise RolloutError(f"{service} image has an invalid digest")
        if image.get("repository") != repository or image.get("ref") != (
            f"{repository}:{value['tag']}@{digest}"
        ):
            raise RolloutError(f"{service} image lacks the immutable release reference")
        if image.get("revision") != value["release_sha"] or image.get("version") != value["version"]:
            raise RolloutError(f"{service} image OCI identity is inconsistent")
    return cast("dict[str, object]", value)


def rollout_token(manifest: dict[str, object]) -> str:
    return f"{manifest['tag']}@{str(manifest['release_sha'])[:12]}"


def image_refs(manifest: dict[str, object]) -> dict[str, str]:
    images = cast("dict[str, dict[str, object]]", manifest["images"])
    return {service: str(image["ref"]) for service, image in images.items()}


def version_spec(image_ref: str, repository: str) -> str:
    if not image_ref.startswith(repository + ":"):
        raise RolloutError("image reference is outside the application repository")
    return image_ref[len(repository) + 1 :]


def revalidate_images(host: str, manifest: dict[str, object]) -> dict[str, object]:
    arch_result = subprocess.run(
        ssh_command(host, ["uname", "-m"]), text=True, capture_output=True, check=False
    )
    if arch_result.returncode:
        raise RolloutError("cannot read the deployment host architecture")
    host_arch = normalized_host_arch(arch_result.stdout)
    inspected: dict[str, object] = {}
    images = cast("dict[str, dict[str, object]]", manifest["images"])
    for service, image in images.items():
        try:
            value = inspect_image(host, str(image["ref"]))
            validate_published_image(
                value,
                release_sha=str(manifest["release_sha"]),
                version=str(manifest["version"]),
                host_arch=host_arch,
            )
        except ReleaseError as exc:
            raise RolloutError(f"{service}: {exc}") from exc
        if value["manifest_digest"] != image["manifest_digest"]:
            raise RolloutError(f"{service}: published digest differs from the release manifest")
        inspected[service] = value
    return {"host_architecture": host_arch, "images": inspected}


def run_deploy(host: str, deploy_root: str, deploy_name: str, spec: str) -> dict[str, object]:
    command = ssh_command(host, [f"{deploy_root}/deploy.sh", "start", deploy_name, "--version", spec])
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    output = redact((result.stdout + result.stderr).strip())[-2000:]
    if result.returncode != 0:
        raise RolloutError(f"deploy.sh start failed ({result.returncode}): {output}")
    return {"command": command[-1], "output_tail": output}


def write_new(path: Path, value: dict[str, object]) -> None:
    if path.exists():
        raise RolloutError(f"refusing to overwrite rollout evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="action", required=True)
    for action in ("plan", "execute"):
        command = subparsers.add_parser(action)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--host", default="capy")
        command.add_argument("--project", default="signaldeck")
        command.add_argument("--backup-root")
        command.add_argument("--backup-compression", type=int, choices=range(10), default=6)
        command.add_argument("--confirm-rollout")
        command.add_argument("--confirm-prune")
        command.add_argument("--observe-seconds", type=int, default=300)
        command.add_argument("--evidence", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest_path = args.manifest.resolve()
    manifest = load_manifest(manifest_path)
    project = validate_project(args.project)
    token = rollout_token(manifest)
    refs = image_refs(manifest)
    prune_token = f"{project}:keep-3"
    if args.confirm_prune not in (None, prune_token):
        raise RolloutError(f"--confirm-prune accepts only {prune_token}")
    plan = {
        "action": args.action,
        "manifest": str(manifest_path),
        "tag": manifest["tag"],
        "release_sha": manifest["release_sha"],
        "images": refs,
        "project": project,
        "confirm_rollout": token,
        "stages": [
            "revalidate images",
            "preflight",
            "schema compatibility",
            "plugin comparison",
            "quiesced backup",
            "deploy.sh start",
            "post-deploy gates",
            "persist version pin",
            f"observe {args.observe_seconds}s",
            "retention " + ("keep-3" if args.confirm_prune else "not_requested"),
        ],
    }
    if args.action == "plan":
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.confirm_rollout != token:
        raise RolloutError(f"execute requires --confirm-rollout {token}")

    base = {"project": project, "backup_root": args.backup_root}
    app_ref = refs["app"]
    evidence: dict[str, object] = {
        "schema_version": 1,
        "status": "running",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "release_manifest": str(manifest_path),
        "tag": manifest["tag"],
        "release_sha": manifest["release_sha"],
        "image_ref": app_ref,
        "stages": {},
    }
    stages = cast("dict[str, object]", evidence["stages"])
    stage = "revalidate images"
    deploy_started = False
    preflight: dict[str, object] = {}
    try:
        stages[stage] = revalidate_images(args.host, manifest)
        stage = "preflight"
        app_repository = str(cast("dict[str, dict[str, object]]", manifest["images"])["app"]["repository"])
        preflight = ssh_python(
            args.host, REMOTE_PREFLIGHT, {**base, "app_repository": app_repository}, timeout=300
        )
        stages[stage] = preflight
        stage = "schema compatibility"
        schema = ssh_python(args.host, REMOTE_SCHEMA_CHECK, {**base, "image_ref": app_ref}, timeout=900)
        stages[stage] = schema
        if not schema["compatible"]:
            raise RolloutError("the release models are incompatible with the live schema")
        stage = "plugin comparison"
        try:
            stages[stage] = ssh_python(
                args.host,
                REMOTE_PLUGIN_COMPARE,
                {**base, "images": {name: ref for name, ref in refs.items() if name != "app"}},
                timeout=1800,
            )
        except OpsError as exc:
            stages[stage] = {"status": "unavailable", "error": str(exc)}
        stage = "quiesced backup"
        backup_command = [
            sys.executable,
            str(BACKUP_SCRIPTS / "signaldeck_backup.py"),
            "execute",
            "--host",
            args.host,
            "--project",
            project,
            "--mode",
            "quiesced",
            "--compression",
            str(args.backup_compression),
            "--confirm-backup",
            project,
        ]
        if args.backup_root:
            backup_command += ["--backup-root", args.backup_root]
        backup_result = subprocess.run(backup_command, text=True, capture_output=True, check=False)
        if backup_result.returncode != 0:
            raise RolloutError(f"backup failed: {redact(backup_result.stderr.strip())[-1500:]}")
        backup = json.loads(backup_result.stdout)
        backup_evidence = ssh_python(
            args.host, REMOTE_READ_BACKUP, {**base, "manifest": backup["manifest"]}, timeout=120
        )
        stages[stage] = {"result": backup, "manifest": backup_evidence}
        topology = cast("dict[str, str]", preflight["topology"])
        deploy_started = True
        stage = "deploy.sh start"
        stages[stage] = run_deploy(
            args.host,
            topology["deploy_root"],
            topology["deploy_name"],
            version_spec(app_ref, app_repository),
        )
        stage = "post-deploy gates"
        stages[stage] = ssh_python(
            args.host,
            REMOTE_POST_DEPLOY,
            {
                **base,
                "image_ref": app_ref,
                "version": manifest["version"],
                "service_images": preflight["service_images"],
                "backup_counts": backup_evidence["counts"],
                "smoke_paths": list(SMOKE_PATHS),
            },
            timeout=None,
        )
        stage = "persist version pin"
        stages[stage] = ssh_python(args.host, REMOTE_PIN, {**base, "image_ref": app_ref}, timeout=300)
        stage = "observe"
        stages[stage] = ssh_python(
            args.host,
            REMOTE_OBSERVE,
            {
                **base,
                "seconds": args.observe_seconds,
                "image_ref": app_ref,
                "version": manifest["version"],
            },
            timeout=args.observe_seconds + 300,
        )
        stage = "retention"
        if args.confirm_prune:
            prune = subprocess.run(
                [
                    sys.executable,
                    str(BACKUP_SCRIPTS / "signaldeck_prune_backups.py"),
                    "execute",
                    "--host",
                    args.host,
                    "--project",
                    project,
                    "--confirm-prune",
                    prune_token,
                    "--protect",
                    str(Path(str(backup["manifest"])).parent),
                ]
                + (["--backup-root", args.backup_root] if args.backup_root else []),
                text=True,
                capture_output=True,
                check=False,
            )
            if prune.returncode != 0:
                raise RolloutError(f"retention failed: {redact(prune.stderr.strip())[-1500:]}")
            stages[stage] = json.loads(prune.stdout)
        else:
            stages[stage] = {"status": "not_requested"}
        evidence["status"] = "complete"
    except (OpsError, RolloutError, ReleaseError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        evidence["status"] = "failed"
        evidence["failed_stage"] = stage
        evidence["error"] = redact(str(exc))
        if deploy_started:
            try:
                evidence["stop_gate"] = ssh_python(args.host, REMOTE_STOP, base, timeout=300)
            except OpsError as stop_error:
                evidence["stop_gate"] = {"status": "failed", "error": str(stop_error)}
            topology = cast("dict[str, str]", preflight["topology"])
            previous = str(preflight["previous_app_image"])
            evidence["rollback_command"] = (
                f"{topology['deploy_root']}/deploy.sh start {topology['deploy_name']} --version "
                + version_spec(previous, str(topology["app_repository"]))
            )
    evidence["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    evidence_path = args.evidence
    if evidence_path is None:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        evidence_path = (
            Path.cwd()
            / "artifacts"
            / "evidence"
            / "signaldeck-ops"
            / "rollouts"
            / f"{stamp}-{manifest['tag']}.json"
        )
    write_new(evidence_path.resolve(), evidence)
    print(
        json.dumps(
            {"evidence": str(evidence_path.resolve()), **evidence},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if evidence["status"] == "complete" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OpsError, RolloutError, ReleaseError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

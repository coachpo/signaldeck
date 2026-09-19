#!/usr/bin/env python3
"""Shared local and remote helpers for SignalDeck operations on a Compose host.

Local code runs on python3 >= 3.9. Remote programs are sent over SSH to the host's
python3 (>= 3.10) and print one JSON object; they never print environment values,
configuration contents or database URLs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path

PROJECT_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}")
SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|token|secret|api[-_ ]?key|credential|authorization|cookie"
    r"|database[_ .-]?url|encryption[_ -]?key)"
)


class OpsError(RuntimeError):
    pass


def redact(value: str) -> str:
    return "\n".join(
        "<redacted secret-bearing line>" if SECRET_PATTERN.search(line) else line
        for line in value.splitlines()
    )


def validate_project(project: str) -> str:
    if not PROJECT_PATTERN.fullmatch(project):
        raise OpsError(f"invalid Compose project name: {project}")
    return project


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def encode_payload(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def ssh_python(
    host: str, program: str, payload: dict[str, object], timeout: int | None = None
) -> dict[str, object]:
    encoded = encode_payload(payload)
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            host,
            "python3",
            "-",
            encoded,
        ],
        input=program,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = redact((result.stderr or result.stdout).strip())
        raise OpsError(f"remote operation failed ({result.returncode}): {detail}")
    if SECRET_PATTERN.search(result.stdout):
        raise OpsError("remote operation returned possible secret-bearing output")
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise OpsError("remote operation did not return JSON") from exc
    if not isinstance(value, dict):
        raise OpsError("remote operation returned a non-object result")
    return value


REMOTE_COMMON = r'''
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

REQUIRED_SERVICES = ("app", "dispatcher", "worker", "db", "temporal")
# Leases, rate state and expiring cache rows may legitimately disappear at any time.
EPHEMERAL_TABLES = frozenset({
    "public.platform_io_resource_permits",
    "public.platform_io_resource_rates",
    "public.platform_read_tool_cache",
})
SECRET_LINE = re.compile(
    r"(?i)(password|passwd|token|secret|api[-_ ]?key|credential|authorization|cookie"
    r"|database[_ .-]?url|encryption[_ -]?key)"
)
PIN_KEY = re.compile(r"(SIGNALDECK_[A-Z0-9_]*VERSION|COMPOSE_PROFILES|SIGNALDECK_PLUGINS)")
DATABASE_NAME = re.compile(r"[a-z_][a-z0-9_]{0,62}")
HTTP_PROBE = """
import json, sys, urllib.error, urllib.request
url = "http://127.0.0.1:" + sys.argv[3] + sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=float(sys.argv[2])) as response:
        status, body = response.status, response.read()
except urllib.error.HTTPError as error:
    status, body = error.code, error.read()
except OSError:
    status, body = 0, b""
print(json.dumps({"status": status, "body": body[:1048576].decode("utf-8", "replace")}))
"""


def payload():
    return json.loads(base64.urlsafe_b64decode(sys.argv[1].encode("ascii")))


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def redacted_tail(raw):
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    lines = ["<redacted>" if SECRET_LINE.search(line) else line for line in text.splitlines()]
    return "\n".join(lines)[-600:]


def run(argv, *, input_stream=None, output_stream=None, env=None, check=True):
    result = subprocess.run(
        argv,
        stdin=input_stream,
        stdout=output_stream if output_stream is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if check and result.returncode != 0:
        command = " ".join(str(item) for item in argv[:4])
        raise RuntimeError(
            f"command failed ({result.returncode}): {command}: {redacted_tail(result.stderr or b'')}"
        )
    if output_stream is not None:
        return ""
    return (result.stdout or b"").decode("utf-8", errors="replace").strip()


def split_image_ref(ref):
    """Return (repository, tag, digest) for repository[:tag][@digest]."""
    name, _, digest = ref.partition("@")
    tag = None
    if ":" in name.rsplit("/", 1)[-1]:
        name, tag = name.rsplit(":", 1)
    return name, tag, digest or None


def compose_rows():
    raw = run(["docker", "compose", "ls", "--all", "--format", "json"])
    if not raw:
        return []
    value = json.loads(raw)
    return value if isinstance(value, list) else [value]


def project_containers(project):
    raw = run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"])
    ids = [line for line in raw.splitlines() if line]
    services = {}
    if not ids:
        return services
    for info in json.loads(run(["docker", "inspect", *ids])):
        labels = info.get("Config", {}).get("Labels") or {}
        if labels.get("com.docker.compose.oneoff") == "True":
            continue
        services.setdefault(labels.get("com.docker.compose.service"), []).append(info)
    return services


def discover(project, backup_root_override=None):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project):
        raise RuntimeError("invalid Compose project name")
    matches = [row for row in compose_rows() if row.get("Name") == project]
    if len(matches) != 1:
        raise RuntimeError(f"expected one Compose project {project}, found {len(matches)}")
    configs = [
        Path(value).resolve()
        for value in str(matches[0].get("ConfigFiles", "")).split(",")
        if value
    ]
    if len(configs) != 1 or not configs[0].is_file():
        raise RuntimeError("expected one readable Compose config file")
    config_file = configs[0]
    service_dir = config_file.parent
    deploy_root = service_dir.parent
    env_file = next(
        (path for path in (service_dir / "backend.env", service_dir / ".env") if path.is_file()),
        None,
    )
    services = project_containers(project)
    for name in REQUIRED_SERVICES:
        if len(services.get(name, [])) != 1:
            raise RuntimeError(f"expected one {name} container, found {len(services.get(name, []))}")
    app_repository = split_image_ref(services["app"][0]["Config"]["Image"])[0]
    app_roles = sorted(
        name
        for name, infos in services.items()
        if all(split_image_ref(info["Config"]["Image"])[0] == app_repository for info in infos)
    )
    if backup_root_override:
        backup_root = Path(backup_root_override)
        if not backup_root.is_absolute():
            raise RuntimeError("backup root must be absolute")
        backup_root = backup_root.resolve()
    else:
        backup_root = (deploy_root / "backups").resolve()
    deploy_name = str(service_dir.relative_to(deploy_root))
    return {
        "project": project,
        "config_file": config_file,
        "service_dir": service_dir,
        "deploy_root": deploy_root,
        "deploy_name": deploy_name,
        "env_file": env_file,
        "app_repository": app_repository,
        "app_roles": app_roles,
        "backup_root": backup_root,
        "version_var": re.sub(r"[^A-Z0-9]", "_", deploy_name.upper()) + "_VERSION",
    }


def public_topology(topology):
    return {
        key: (str(value) if isinstance(value, Path) else value)
        for key, value in topology.items()
    }


def container_id(topology, service):
    infos = project_containers(topology["project"]).get(service, [])
    if len(infos) != 1:
        raise RuntimeError(f"expected one {service} container, found {len(infos)}")
    return infos[0]["Id"]


def inspect(container):
    return json.loads(run(["docker", "inspect", container]))[0]


def safe_state(info):
    state = info.get("State", {})
    health = state.get("Health") or {}
    return {
        "container": info.get("Id", "")[:12],
        "image_ref": info.get("Config", {}).get("Image"),
        "image_id": info.get("Image"),
        "status": state.get("Status"),
        "health": health.get("Status"),
        "exit_code": state.get("ExitCode"),
        "restarts": info.get("RestartCount"),
        "started_at": state.get("StartedAt"),
    }


def service_state(topology, service):
    return safe_state(inspect(container_id(topology, service)))


def image_labels(image_id):
    image = json.loads(run(["docker", "image", "inspect", image_id]))[0]
    return image.get("Config", {}).get("Labels") or {}


def immutable_image_ref(info):
    configured = info.get("Config", {}).get("Image")
    if not isinstance(configured, str) or not configured:
        raise RuntimeError("container has no configured image reference")
    if "@sha256:" in configured:
        return configured
    image_info = json.loads(run(["docker", "image", "inspect", info.get("Image")]))[0]
    repository = split_image_ref(configured)[0]
    matches = [
        value
        for value in image_info.get("RepoDigests") or []
        if value.startswith(repository + "@sha256:")
    ]
    if len(matches) != 1:
        raise RuntimeError("cannot resolve one immutable digest for the configured image")
    return configured + "@" + matches[0].split("@", 1)[1]


def compose_argv(topology, *tail):
    argv = ["docker", "compose"]
    if topology["env_file"]:
        argv += ["--env-file", str(topology["env_file"])]
    argv += ["-f", str(topology["config_file"])]
    return argv + list(tail)


def psql(topology, sql, database="postgres"):
    if database != "postgres" and not DATABASE_NAME.fullmatch(database):
        raise RuntimeError("invalid database name")
    command = (
        'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d '
        + shlex.quote(database)
        + ' -AtF "|" -qc '
        + shlex.quote(sql)
    )
    return run(["docker", "exec", container_id(topology, "db"), "sh", "-c", command])


def sql_literal(value):
    return "'" + value.replace("'", "''") + "'"


def databases(topology):
    rows = psql(
        topology,
        "SELECT d.datname, r.rolname, pg_database_size(d.datname) FROM pg_database d "
        "JOIN pg_roles r ON r.oid = d.datdba "
        "WHERE NOT d.datistemplate AND d.datname <> 'postgres' ORDER BY 1",
    )
    result = []
    for line in rows.splitlines():
        if not line:
            continue
        name, owner, size = line.split("|")
        if not DATABASE_NAME.fullmatch(name) or not DATABASE_NAME.fullmatch(owner):
            raise RuntimeError("unexpected database or owner name")
        result.append({"name": name, "owner": owner, "size_bytes": int(size)})
    return result


def is_engine_database(name):
    # Temporal owns these history databases; their row counts change with every timer.
    return "temporal" in name


def table_counts(topology, database):
    tables = [
        line
        for line in psql(
            topology,
            "SELECT quote_ident(schemaname) || '.' || quote_ident(tablename) FROM pg_tables "
            "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') ORDER BY 1",
            database,
        ).splitlines()
        if line
    ]
    if not tables:
        return {}
    query = " UNION ALL ".join(f"SELECT {sql_literal(name)}, count(*) FROM {name}" for name in tables)
    counts = {}
    for line in psql(topology, query, database).splitlines():
        name, count = line.rsplit("|", 1)
        counts[name] = int(count)
    return counts


def count_regressions(before, after):
    """Durable tables whose row count decreased; ephemeral tables are ignored."""
    regressions = []
    for database, tables in before.items():
        for table, count in tables.items():
            if table in EPHEMERAL_TABLES:
                continue
            current = after.get(database, {}).get(table)
            if current is None or current < count:
                regressions.append({"database": database, "table": table, "before": count, "after": current})
    return regressions


def application_counts(topology):
    return {
        item["name"]: table_counts(topology, item["name"])
        for item in databases(topology)
        if not is_engine_database(item["name"])
    }


def app_http(topology, path, timeout=10):
    info = inspect(container_id(topology, "app"))
    environment = dict(
        item.split("=", 1) for item in info.get("Config", {}).get("Env") or [] if "=" in item
    )
    raw = run([
        "docker", "exec", info["Id"], "python", "-c", HTTP_PROBE,
        path, str(timeout), environment.get("PORT", "8080"),
    ])
    value = json.loads(raw)
    return value["status"], value["body"]


def wait_app_ready(topology, expected_version=None, deadline_seconds=600, interval=5):
    deadline = time.monotonic() + deadline_seconds
    last = "not checked"
    while time.monotonic() < deadline:
        try:
            state = service_state(topology, "app")
            if state["status"] == "running" and state["health"] == "healthy":
                ready_status, _ = app_http(topology, "/ready")
                health_status, health_body = app_http(topology, "/health")
                health = json.loads(health_body) if health_status == 200 else {}
                if ready_status == 200 and health.get("status") == "ok" and (
                    expected_version is None or health.get("version") == expected_version
                ):
                    return health
                last = f"ready={ready_status} health={health}"
            else:
                last = f"app {state['status']}/{state['health']}"
        except (RuntimeError, ValueError, KeyError) as exc:
            last = str(exc)
        time.sleep(interval)
    raise RuntimeError(f"app readiness deadline exceeded: {last}")


def env_pins(topology):
    """Only version, profile and plugin selections; every other line stays unread."""
    pins = {}
    if topology["env_file"] is None:
        return pins
    for line in Path(topology["env_file"]).read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and PIN_KEY.fullmatch(key.strip()):
            pins[key.strip()] = value.strip().strip("'\"")
    return pins


def replace_env_value(text, key, value):
    lines = text.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.partition("=")[0].strip() == key]
    if len(matches) > 1:
        raise RuntimeError(f"expected at most one {key} line, found {len(matches)}")
    if not matches:
        prefix = "" if not lines or lines[-1].endswith("\n") else "\n"
        return text + f"{prefix}{key}={value}\n"
    index = matches[0]
    lines[index] = f"{key}={value}" + ("\n" if lines[index].endswith("\n") else "")
    return "".join(lines)


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def checksum_entries(path):
    entries = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "  " in line:
            digest, name = line.split("  ", 1)
            entries[name] = digest
    return entries


def manifest_artifact_names(manifest):
    names = set(manifest["configs"].values())
    for item in manifest["databases"]:
        names |= {item["dump"], item["list"]}
    for item in manifest["volumes"].values():
        names.add(item["archive"])
    return names


def validate_backup(backup_dir, project=None, verify_hashes=True):
    """Return the manifest of a complete managed backup, or raise ValueError."""
    try:
        if backup_dir.is_symlink() or not backup_dir.is_dir():
            raise ValueError("not a real backup directory")
        if (backup_dir / ".incomplete").exists():
            raise ValueError("backup is incomplete")
        manifest_path = backup_dir / "manifest.json"
        sums_path = backup_dir / "SHA256SUMS"
        for path in (manifest_path, sums_path):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"missing {path.name}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1 or manifest.get("status") != "verified":
            raise ValueError("manifest is not a verified schema-version-1 backup")
        if project is not None and manifest.get("project") != project:
            raise ValueError("manifest belongs to another project")
        artifacts = manifest["artifacts"]
        sums = checksum_entries(sums_path)
        if not artifacts or set(artifacts) != set(sums) or set(artifacts) != manifest_artifact_names(manifest):
            raise ValueError("artifact lists differ between manifest, contents and SHA256SUMS")
        real = backup_dir.resolve()
        for name, evidence in artifacts.items():
            item = backup_dir / name
            if evidence.get("path") != name or Path(name).name != name:
                raise ValueError(f"unsafe artifact path: {name}")
            if item.is_symlink() or not item.is_file() or item.resolve().parent != real:
                raise ValueError(f"artifact is not a regular file: {name}")
            if sums[name] != evidence.get("sha256"):
                raise ValueError(f"SHA256SUMS differs from the manifest: {name}")
            if verify_hashes and file_sha(item) != evidence["sha256"]:
                raise ValueError(f"artifact bytes differ from the manifest: {name}")
        preflight = manifest["preflight"]
        if preflight.get("path") != "preflight.json" or (
            verify_hashes and file_sha(backup_dir / "preflight.json") != preflight.get("sha256")
        ):
            raise ValueError("preflight evidence differs from the manifest")
        return manifest
    except (OSError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"malformed backup: {type(exc).__name__}") from exc


def stop_services(topology, services, timeout=60):
    run(compose_argv(topology, "stop", "-t", str(timeout), *services))


def start_services(topology, services):
    run(compose_argv(topology, "start", *services))


def restart_quiesced(topology, stopped):
    if "temporal" in stopped:
        start_services(topology, ["temporal"])
    remaining = [name for name in ("dispatcher", "worker", "app") if name in stopped]
    if remaining:
        start_services(topology, remaining)
    return wait_app_ready(topology)
'''

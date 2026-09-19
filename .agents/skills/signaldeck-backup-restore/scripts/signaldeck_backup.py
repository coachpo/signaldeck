#!/usr/bin/env python3
"""Plan or execute a verified SignalDeck database, volume and configuration backup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from signaldeck_ops_common import REMOTE_COMMON, OpsError, ssh_python, validate_project

REMOTE_BACKUP = (
    REMOTE_COMMON
    + r'''
# Quiescing these stops every writer: the gateway, command delivery, pinned workers
# and Temporal timers. PostgreSQL and the idle plugins keep running.
QUIESCE = ("app", "dispatcher", "worker", "temporal")
# Logical dumps cover PostgreSQL, and the uv cache is re-downloadable.
EXCLUDED_VOLUME_DESTINATIONS = frozenset({"/var/lib/postgresql/data", "/data/uv-cache"})
CONFIG_FILES = ("backend.env", "compose.yml", "plugin-defaults.json")


def backup_volumes(topology):
    names = set(run([
        "docker", "volume", "ls", "-q",
        "--filter", f"label=com.docker.compose.project={topology['project']}",
    ]).split())
    excluded = set()
    for infos in project_containers(topology["project"]).values():
        for info in infos:
            for mount in info.get("Mounts", []):
                if (
                    mount.get("Type") == "volume"
                    and mount.get("Destination") in EXCLUDED_VOLUME_DESTINATIONS
                ):
                    excluded.add(mount.get("Name"))
    return sorted(names - excluded), sorted(names & excluded)


def helper_image(topology):
    # The digest-pinned PostgreSQL image is always present and provides tar, gzip and du.
    return inspect(container_id(topology, "db"))["Image"]


def volume_size(topology, volume):
    raw = run([
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "du",
        "-v", f"{volume}:/source:ro", helper_image(topology), "-sk", "/source",
    ])
    return int(raw.split()[0]) * 1024


def archive_volume(topology, volume, destination):
    with destination.open("wb") as output:
        run([
            "docker", "run", "--rm", "--network", "none", "--entrypoint", "tar",
            "-v", f"{volume}:/source:ro", helper_image(topology),
            "-C", "/source", "-czf", "-", ".",
        ], output_stream=output)
    os.chmod(destination, 0o600)
    with destination.open("rb") as archive:
        listing = run([
            "docker", "run", "--rm", "-i", "--network", "none", "--entrypoint", "tar",
            helper_image(topology), "-tzf", "-",
        ], input_stream=archive)
    return len([line for line in listing.splitlines() if line])


def dump_database(topology, database, compression, destination):
    command = (
        f"exec pg_dump -Fc --compress={int(compression)} --no-owner --no-acl "
        + '-U "$POSTGRES_USER" -d '
        + shlex.quote(database)
    )
    with destination.open("wb") as output:
        run(["docker", "exec", container_id(topology, "db"), "sh", "-c", command], output_stream=output)
    os.chmod(destination, 0o600)
    if destination.stat().st_size == 0:
        raise RuntimeError(f"pg_dump produced an empty archive for {database}")
    listing = destination.with_suffix(".list")
    with destination.open("rb") as archive, listing.open("wb") as output:
        run(
            ["docker", "exec", "-i", container_id(topology, "db"), "pg_restore", "--list"],
            input_stream=archive,
            output_stream=output,
        )
    os.chmod(listing, 0o600)
    if listing.stat().st_size == 0:
        raise RuntimeError(f"pg_restore --list produced no evidence for {database}")
    return listing.name


def backup_main():
    args = payload()
    topology = discover(args["project"], args.get("backup_root"))
    states = {name: service_state(topology, name) for name in ("app", "db", "temporal")}
    if any(state["health"] != "healthy" for state in states.values()):
        raise RuntimeError("app, db and temporal must be healthy before backup")
    volumes, excluded_volumes = backup_volumes(topology)
    volume_sizes = {volume: volume_size(topology, volume) for volume in volumes}
    database_list = databases(topology)
    service_root = topology["backup_root"] / topology["project"]
    plan = {
        "action": args["action"],
        "project": topology["project"],
        "mode": args["mode"],
        "compression": args["compression"],
        "backup_root": str(service_root),
        "quiesce": list(QUIESCE) if args["mode"] == "quiesced" else [],
        "databases": database_list,
        "volumes": volume_sizes,
        "excluded_volumes": excluded_volumes,
        "config_files": [name for name in CONFIG_FILES if (topology["service_dir"] / name).is_file()],
        "restart_on_success": args["restart_on_success"],
    }
    if args["action"] == "plan":
        print(json.dumps(plan, sort_keys=True))
        return
    if args.get("confirm_backup") != topology["project"]:
        raise RuntimeError("confirmation token must equal the Compose project name")
    service_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(service_root, 0o700)
    database_bytes = sum(item["size_bytes"] for item in database_list)
    required = (
        database_bytes * (8 if args["compression"] == 0 else 2)
        + sum(volume_sizes.values())
        + 5 * 1024**3
    )
    free = shutil.disk_usage(service_root).free
    if free <= required:
        raise RuntimeError(f"insufficient backup capacity: required>{required} free={free}")
    backup_dir = service_root / f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}-managed"
    backup_dir.mkdir(mode=0o700)
    incomplete = backup_dir / ".incomplete"
    incomplete.write_text("backup in progress\n", encoding="utf-8")
    os.chmod(incomplete, 0o600)
    stopped = []
    try:
        if args["mode"] == "quiesced":
            stopped = list(QUIESCE)
            stop_services(topology, QUIESCE)
            if service_state(topology, "db")["health"] != "healthy":
                raise RuntimeError("PostgreSQL became unhealthy after quiescing")
        # Capture the evidence after quiescing so it describes the archived state.
        database_list = databases(topology)
        counts = application_counts(topology)
        images = {
            service: immutable_image_ref(infos[0])
            for service, infos in sorted(project_containers(topology["project"]).items())
            if len(infos) == 1
        }
        configs = {}
        for name in CONFIG_FILES:
            source = topology["service_dir"] / name
            if source.is_file():
                copy = backup_dir / f"config-{name}"
                shutil.copyfile(source, copy)
                os.chmod(copy, 0o600)
                configs[name] = copy.name
        preflight = {
            "schema_version": 1,
            "observed_at": utc_now().isoformat(),
            "topology": public_topology(topology),
            "states": states,
            "images": images,
            "env_pins": env_pins(topology),
            "databases": database_list,
            "counts": counts,
            "evidence_consistency": (
                "quiesced_exact" if args["mode"] == "quiesced" else "online_advisory"
            ),
        }
        write_atomic(backup_dir / "preflight.json", preflight)
        artifacts = []
        database_entries = []
        for item in database_list:
            dump = backup_dir / f"db-{item['name']}.dump"
            listing = dump_database(topology, item["name"], args["compression"], dump)
            artifacts += [dump.name, listing]
            database_entries.append({**item, "dump": dump.name, "list": listing})
        volume_entries = {}
        for volume in volumes:
            archive = backup_dir / f"volume-{volume}.tar.gz"
            entries = archive_volume(topology, volume, archive)
            artifacts.append(archive.name)
            volume_entries[volume] = {
                "archive": archive.name,
                "entries": entries,
                "size_bytes": volume_sizes[volume],
            }
        artifacts += list(configs.values())
        hashes = {name: file_sha(backup_dir / name) for name in artifacts}
        sums = backup_dir / "SHA256SUMS"
        sums.write_text("".join(f"{hashes[name]}  {name}\n" for name in sorted(hashes)), encoding="utf-8")
        os.chmod(sums, 0o600)
        for name, expected in hashes.items():
            if file_sha(backup_dir / name) != expected:
                raise RuntimeError(f"independent checksum verification failed: {name}")
        manifest = {
            "schema_version": 1,
            "status": "verified",
            "created_at": utc_now().isoformat(),
            "project": topology["project"],
            "host": args["host"],
            "backup_mode": args["mode"],
            "compression": args["compression"],
            "evidence_consistency": preflight["evidence_consistency"],
            "source_images": images,
            "app_image_ref": images.get("app"),
            "db_image_ref": images.get("db"),
            "env_pins": preflight["env_pins"],
            "databases": database_entries,
            "counts": counts,
            "volumes": volume_entries,
            "excluded_volumes": excluded_volumes,
            "configs": configs,
            "artifacts": {
                name: {
                    "path": name,
                    "sha256": digest,
                    "size_bytes": (backup_dir / name).stat().st_size,
                }
                for name, digest in hashes.items()
            },
            "preflight": {"path": "preflight.json", "sha256": file_sha(backup_dir / "preflight.json")},
        }
        write_atomic(backup_dir / "manifest.json", manifest)
        incomplete.unlink()
        if stopped and args["restart_on_success"]:
            restart_quiesced(topology, stopped)
            stopped = []
        print(json.dumps({
            "status": "verified",
            "backup_dir": str(backup_dir),
            "manifest": str(backup_dir / "manifest.json"),
            "stopped": stopped,
            "plan": plan,
        }, sort_keys=True))
    except Exception as primary_error:
        if stopped:
            try:
                restart_quiesced(topology, stopped)
            except Exception as recovery_error:
                raise RuntimeError(
                    f"backup failed and restarting the quiesced services also failed: "
                    f"{primary_error}; recovery: {recovery_error}"
                ) from primary_error
        raise


if __name__ == "__main__":
    try:
        backup_main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
'''
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="action", required=True)
    for action in ("plan", "execute"):
        command = subparsers.add_parser(action)
        command.add_argument("--host", default="capy")
        command.add_argument("--project", default="signaldeck")
        command.add_argument("--mode", choices=("quiesced", "online"), default="quiesced")
        command.add_argument("--compression", type=int, choices=range(10), default=6)
        command.add_argument("--backup-root", help="absolute remote backup root override")
        command.add_argument("--restart-on-success", action="store_true")
        command.add_argument("--confirm-backup")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project = validate_project(args.project)
    if args.backup_root and not Path(args.backup_root).is_absolute():
        raise OpsError("--backup-root must be an absolute remote path")
    if args.action == "execute" and args.confirm_backup != project:
        raise OpsError(f"execute requires --confirm-backup {project}")
    payload = {
        "action": args.action,
        "host": args.host,
        "project": project,
        "mode": args.mode,
        "compression": args.compression,
        "backup_root": args.backup_root,
        "restart_on_success": args.restart_on_success,
        "confirm_backup": args.confirm_backup,
    }
    result = ssh_python(args.host, REMOTE_BACKUP, payload, timeout=None)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OpsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

#!/usr/bin/env python3
"""Prove a SignalDeck backup restores, inside a disposable PostgreSQL container.

The drill never touches the live stack: it validates the manifest and checksums,
restores every database dump into a throwaway container of the same PostgreSQL
image without networking, compares row counts, lists every volume archive and
removes the container. Switching a live instance to a backup is a separate,
explicitly authorized procedure described in references/restore.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import PurePosixPath

from signaldeck_ops_common import REMOTE_COMMON, OpsError, ssh_python

REMOTE_RESTORE_CHECK = (
    REMOTE_COMMON
    + r'''
def load_backup(manifest_path):
    manifest_path = Path(manifest_path)
    if manifest_path.name != "manifest.json" or manifest_path.is_symlink():
        raise RuntimeError("manifest path must name a regular manifest.json")
    try:
        manifest = validate_backup(manifest_path.parent)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    return manifest_path.parent, manifest


def drill_psql(container, sql, database="postgres"):
    if database != "postgres" and not DATABASE_NAME.fullmatch(database):
        raise RuntimeError("invalid database name")
    return run([
        "docker", "exec", container, "psql", "-X", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", database, "-AtF", "|", "-qc", sql,
    ])


def drill_counts(container, database):
    tables = [
        line
        for line in drill_psql(
            container,
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
    for line in drill_psql(container, query, database).splitlines():
        name, count = line.rsplit("|", 1)
        counts[name] = int(count)
    return counts


def restore_check_main():
    args = payload()
    backup_dir, manifest = load_backup(args["manifest"])
    image = manifest.get("db_image_ref")
    if not image or "@sha256:" not in image:
        raise RuntimeError("manifest lacks the immutable PostgreSQL image reference")
    token = file_sha(backup_dir / "manifest.json")[:12]
    plan = {
        "action": args["action"],
        "manifest": str(backup_dir / "manifest.json"),
        "confirm_drill": token,
        "image": image,
        "databases": [item["name"] for item in manifest["databases"]],
        "volumes": sorted(manifest.get("volumes", {})),
    }
    if args["action"] == "plan":
        print(json.dumps(plan, sort_keys=True))
        return
    if args.get("confirm_drill") != token:
        raise RuntimeError("confirmation token must equal the manifest hash prefix")
    container = "signaldeck-restore-check-" + utc_now().strftime("%Y%m%dt%H%M%Sz")
    run([
        "docker", "run", "-d", "--name", container, "--network", "none",
        "-e", "POSTGRES_HOST_AUTH_METHOD=trust", image,
    ])
    try:
        # The image entrypoint initializes with a temporary server and then restarts,
        # so wait for the completed initialization before the first connection.
        deadline = time.monotonic() + 120
        while True:
            logs = subprocess.run(["docker", "logs", container], capture_output=True)
            probe = subprocess.run(
                ["docker", "exec", container, "pg_isready", "-U", "postgres"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if b"PostgreSQL init process complete" in logs.stdout + logs.stderr and probe.returncode == 0:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("disposable PostgreSQL did not become ready")
            time.sleep(1)
        drill_psql(container, "SELECT 1")
        databases_result = {}
        for item in manifest["databases"]:
            name, owner = item["name"], item["owner"]
            if not DATABASE_NAME.fullmatch(name) or not DATABASE_NAME.fullmatch(owner):
                raise RuntimeError("invalid database or owner name in manifest")
            if drill_psql(container, f"SELECT 1 FROM pg_roles WHERE rolname = {sql_literal(owner)}") != "1":
                drill_psql(container, f'CREATE ROLE "{owner}"')
            drill_psql(container, f'CREATE DATABASE "{name}" OWNER "{owner}"')
            with (backup_dir / item["dump"]).open("rb") as archive:
                run([
                    "docker", "exec", "-i", container, "pg_restore", "-U", "postgres",
                    "--single-transaction", "--exit-on-error", "--no-owner", "--no-acl",
                    f"--role={owner}", "-d", name,
                ], input_stream=archive)
            restored = drill_counts(container, name)
            expected = manifest.get("counts", {}).get(name)
            if expected is not None and manifest.get("evidence_consistency") == "quiesced_exact":
                if restored != expected:
                    raise RuntimeError(f"restored row counts differ from the manifest for {name}")
            databases_result[name] = {"tables": len(restored), "rows": sum(restored.values())}
        volumes_result = {}
        for volume, item in sorted(manifest.get("volumes", {}).items()):
            with (backup_dir / item["archive"]).open("rb") as archive:
                listing = run([
                    "docker", "run", "--rm", "-i", "--network", "none", "--entrypoint", "tar",
                    image, "-tzf", "-",
                ], input_stream=archive)
            entries = len([line for line in listing.splitlines() if line])
            if entries != item["entries"]:
                raise RuntimeError(f"volume archive entry count differs: {volume}")
            volumes_result[volume] = {"entries": entries}
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(json.dumps({
        "status": "restorable",
        "manifest": plan["manifest"],
        "databases": databases_result,
        "volumes": volumes_result,
        "container_removed": container,
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        restore_check_main()
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
        command.add_argument("--manifest", required=True, help="absolute remote manifest.json path")
        command.add_argument("--confirm-drill")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest = PurePosixPath(args.manifest)
    if not manifest.is_absolute() or manifest.name != "manifest.json":
        raise OpsError("--manifest must be an absolute remote path to manifest.json")
    result = ssh_python(
        args.host,
        REMOTE_RESTORE_CHECK,
        {"action": args.action, "manifest": str(manifest), "confirm_drill": args.confirm_drill},
        timeout=None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OpsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

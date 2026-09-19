#!/usr/bin/env python3
"""Plan or execute strict keep-3 retention for managed SignalDeck backups."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import PurePosixPath

from signaldeck_ops_common import REMOTE_COMMON, OpsError, ssh_python, validate_project

REMOTE_PRUNE = (
    REMOTE_COMMON
    + r'''
def eligible_backups(service_root, project, protected):
    values = []
    if not service_root.is_dir():
        return values
    root_real = service_root.resolve()
    for child in service_root.iterdir():
        if child.is_symlink() or not child.is_dir() or child.resolve().parent != root_real:
            continue
        try:
            manifest = validate_backup(child, project)
        except ValueError:
            continue
        values.append({
            "path": child,
            "created_at": manifest.get("created_at") or child.name,
            "protected": str(child.resolve()) in protected,
        })
    return sorted(values, key=lambda item: item["created_at"], reverse=True)


def select_candidates(managed, keep):
    retained = {str(item["path"].resolve()) for item in managed[:keep]}
    candidates = [
        item
        for item in managed
        if not item["protected"] and str(item["path"].resolve()) not in retained
    ]
    return retained, candidates


def prune_main():
    args = payload()
    topology = discover(args["project"], args.get("backup_root"))
    service_root = (topology["backup_root"] / topology["project"]).resolve()
    protected = {str(Path(value).resolve()) for value in args.get("protect", [])}
    managed = eligible_backups(service_root, topology["project"], protected)
    retained, candidates = select_candidates(managed, args["keep"])
    result = {
        "action": args["action"],
        "project": topology["project"],
        "keep": args["keep"],
        "managed_count": len(managed),
        "retained": [
            str(item["path"])
            for item in managed
            if item["protected"] or str(item["path"].resolve()) in retained
        ],
        "candidates": [str(item["path"]) for item in candidates],
        "deleted": [],
    }
    if args["action"] == "execute":
        expected = f"{topology['project']}:keep-{args['keep']}"
        if args.get("confirm_prune") != expected:
            raise RuntimeError(f"confirmation token must equal {expected}")
        refreshed = eligible_backups(service_root, topology["project"], protected)
        _, refreshed_candidates = select_candidates(refreshed, args["keep"])
        if [str(item["path"].resolve()) for item in refreshed_candidates] != [
            str(item["path"].resolve()) for item in candidates
        ]:
            raise RuntimeError("retention inventory drifted before deletion")
        # Re-resolve each exact, revalidated target immediately before deletion.
        for item in refreshed_candidates:
            target = item["path"]
            if target.is_symlink() or not target.is_dir() or target.resolve().parent != service_root:
                raise RuntimeError("retention target drifted before deletion")
            shutil.rmtree(target)
            result["deleted"].append(str(target))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        prune_main()
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
        command.add_argument("--backup-root")
        command.add_argument("--keep", type=int, default=3)
        command.add_argument("--protect", action="append", default=[])
        command.add_argument("--confirm-prune")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project = validate_project(args.project)
    if args.backup_root and not PurePosixPath(args.backup_root).is_absolute():
        raise OpsError("--backup-root must be an absolute remote path")
    if args.keep != 3:
        raise OpsError("this project policy requires --keep 3")
    expected = f"{project}:keep-3"
    if args.action == "execute" and args.confirm_prune != expected:
        raise OpsError(f"execute requires --confirm-prune {expected}")
    result = ssh_python(
        args.host,
        REMOTE_PRUNE,
        {
            "action": args.action,
            "project": project,
            "backup_root": args.backup_root,
            "keep": args.keep,
            "protect": args.protect,
            "confirm_prune": args.confirm_prune,
        },
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

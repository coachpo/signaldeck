#!/usr/bin/env python3
"""Execute one immutable personal-use GOAL case against fresh source-bound evidence."""

from __future__ import annotations

import argparse
import json
import os
import traceback
from pathlib import Path

from goal_verification.case_evidence import materialize, write_json
from goal_verification.workspace import ROOT, group_result, snapshot, source_identity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--goal", choices=["sd-personal-use-all-sprints", "sd-observed-gaps"], required=True
    )
    parser.add_argument("--case", required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    evidence = Path(os.environ["CLOSED_LOOP_EVIDENCE_DIR"]).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    plan = json.loads((ROOT / ".steward/goals" / args.goal / "acceptance-plan.json").read_text())
    case = next(value for value in plan["cases"] if value["id"] == args.case)
    recipes = json.loads((Path(__file__).parent / "goal_verification/recipes.json").read_text())
    recipe = recipes[args.case]
    results, folders = {}, {}
    try:
        identity, entries = source_identity()
        workspace, _ = snapshot(args.session, identity, entries)
        for group in recipe["groups"]:
            print(json.dumps({"case": args.case, "group": group, "state": "checking"}), flush=True)
            result, folder = group_result(args.session, identity, entries, group)
            results[group], folders[group] = result, folder
            if not result.get("passed"):
                raise AssertionError("Required verification group failed: " + group)
        materialize(case, recipe, identity, workspace, results, folders, evidence)
        if source_identity()[0] != identity:
            raise AssertionError("Source changed during case acceptance")
        print(json.dumps({"case": args.case, "passed": True, "groups": list(results)}), flush=True)
        return 0
    except Exception as error:
        write_json(
            evidence / "runner-failure.json",
            {
                "case": args.case,
                "errorType": type(error).__name__,
                "error": str(error),
                "groups": results,
            },
        )
        (evidence / "runner-error.log").write_text(traceback.format_exc())
        logs = ["# Failed case " + args.case + "\n"]
        for group, folder in folders.items():
            p = folder / "checks.log"
            if p.exists():
                logs.append("\n# " + group + "\n" + p.read_text(errors="replace"))
        (evidence / "checks.log").write_text("".join(logs))
        print(
            json.dumps({"case": args.case, "passed": False, "errorType": type(error).__name__}),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Bind executed tests and original runtime artifacts to each frozen case contract."""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

from goal_verification.workspace import ROOT, sha


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def test_coverage(results: dict, patterns: list[str]) -> list[dict]:
    names = [name for result in results.values() for name in result.get("testNames", [])]
    covered = []
    for pattern in patterns:
        matching = [name for name in names if re.search(pattern, name, re.IGNORECASE)]
        if not matching:
            raise AssertionError("Required executed test coverage is missing: " + pattern)
        covered.append({"pattern": pattern, "executedTests": matching})
    return covered


def assertion_sources(workspace: Path, coverage: list[dict]) -> list[dict]:
    names = "\n".join(name for item in coverage for name in item["executedTests"])
    sources = []
    for path in sorted((workspace / "backend/tests").glob("test_*.py")):
        if path.stem not in names:
            continue
        text = path.read_text()
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("test_") and node.name in names:
                sources.append(
                    {
                        "path": path.relative_to(workspace).as_posix(),
                        "line": node.lineno,
                        "name": node.name,
                        "sourceSha256": sha(path.read_bytes()),
                        "assertions": [
                            ast.get_source_segment(text, value)
                            for value in ast.walk(node)
                            if isinstance(value, ast.Assert)
                        ],
                    }
                )
    return sources


def document_review() -> dict:
    paths = [
        "docs/planning/personal-use-implementation-plan.md",
        "docs/planning/personal-use-sprint-backlog.md",
        "docs/planning/personal-use-verification.md",
        "docs/planning/observed-gaps-verification.md",
        "docs/产品说明.md",
        "docs/架构说明.md",
        "docs/开发规范.md",
        "docs/data-model.md",
        "docs/writing-extensions.md",
        "plugins/notes/README.md",
        "STATUS.md",
        "CONTRIBUTING.md",
    ]
    missing = []
    for name in paths:
        path = ROOT / name
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            target = target.split("#")[0].strip("<>")
            if target and not (path.parent / target).exists():
                missing.append({"document": name, "target": target})
    if missing:
        raise AssertionError(
            "Broken document references: " + json.dumps(missing, ensure_ascii=False)
        )
    backlog = (ROOT / paths[1]).read_text()
    ids = re.findall(r"^### (pu-[a-z0-9-]+) —", backlog, re.MULTILINE)
    if len(ids) != 24 or len(set(ids)) != 24:
        raise AssertionError("The 24-task delivery scope changed")
    delivery = (ROOT / paths[2]).read_text()
    if any(case_id not in delivery for case_id in ids):
        raise AssertionError("The delivery index omits a planned task")
    status = (ROOT / "STATUS.md").read_text()
    if "开发档位：MVP" not in status or "个人" not in status:
        raise AssertionError("The personal MVP boundary changed")
    result = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--check"], capture_output=True, text=True
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return {
        "documents": paths,
        "taskIds": ids,
        "linksChecked": True,
        "diffCheck": True,
        "reviewBoundary": (
            "References, delivery mapping and scope are checked here; "
            "behavioral proof is the attached executed native and runtime evidence."
        ),
    }


def materialize(
    case: dict,
    recipe: dict,
    identity: str,
    workspace: Path,
    results: dict,
    folders: dict[str, Path],
    evidence: Path,
) -> None:
    if not all(value.get("passed") for value in results.values()):
        raise AssertionError("A required current-source verification group failed")
    coverage = test_coverage(results, recipe["requiredTestPatterns"])
    evidence.mkdir(parents=True, exist_ok=True)
    original = []
    checks = []
    for group, folder in folders.items():
        log = folder / "checks.log"
        if not log.is_file():
            raise AssertionError("A verification group has no command log: " + group)
        checks.append("\n# Native group " + group + "\n" + log.read_text(errors="replace"))
        for filename in (
            "tests.xml",
            "tests.json",
            "stages.json",
            "result.json",
            "real-summary.json",
        ):
            source = folder / filename
            if source.is_file():
                dest = evidence / "native" / group / filename
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
    for declaration in recipe["observedArtifacts"]:
        group, relative = declaration.split(":", 1)
        source = folders[group] / relative
        if not source.is_file() or source.stat().st_size == 0:
            raise AssertionError("Required fresh runtime artifact missing: " + declaration)
        # Retain original bytes beside the index instead of replacing them with a summary.
        target = evidence / "observed" / group / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        original.append(
            {
                "group": group,
                "path": target.relative_to(evidence).as_posix(),
                "sha256": sha(source.read_bytes()),
            }
        )
    proof = {
        "case": case["id"],
        "sourceIdentity": identity,
        "assertion": case["assertion"],
        "executedCoverage": coverage,
        "observedArtifacts": original,
        "nativeGroups": {
            group: {"passed": value["passed"], "testCount": len(value.get("testNames", []))}
            for group, value in results.items()
        },
        "evidenceSemantics": (
            "This index links actual executed checks and unmodified runtime artifacts; "
            "it does not manufacture runtime values from expected assertions."
        ),
    }
    write_json(evidence / "native-assertions.json", assertion_sources(workspace, coverage))
    review = document_review() if recipe.get("final") else None
    if review:
        proof["documentReview"] = review
    for name in case["evidence"]["requiredFiles"]:
        target = evidence / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name == "checks.log":
            target.write_text("".join(checks))
        elif name.endswith(".png"):
            if "real" not in folders or "image" not in recipe:
                raise AssertionError("No actual screenshot mapping for " + name)
            width = Path(name).stem
            source = folders["real"] / "screenshots" / f"{recipe['image']}-{width}.png"
            if not source.is_file() or source.stat().st_size == 0:
                raise AssertionError("Required actual screenshot missing: " + str(source))
            shutil.copy2(source, target)
        elif name == "export.md":
            shutil.copy2(folders["real"] / "export.md", target)
        elif name.endswith(".json"):
            write_json(target, {"evidencePurpose": name, **proof})
        else:
            text = "# " + case["id"] + " — " + name + "\n\n"
            text += case["assertion"] + "\n\n"
            text += (
                "以下为本次实际检查与原始证据索引。"
                "JSON/Markdown原件随本用例保存，非历史报告替代。\n\n"
            )
            text += "```json\n" + json.dumps(proof, ensure_ascii=False, indent=2) + "\n```\n"
            target.write_text(text)
    for name in case["evidence"]["nonEmptyFiles"]:
        if not (evidence / name).is_file() or (evidence / name).stat().st_size == 0:
            raise AssertionError("Missing nonempty case evidence: " + name)

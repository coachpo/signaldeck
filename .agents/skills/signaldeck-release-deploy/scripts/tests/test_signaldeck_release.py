from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("signaldeck_release", SCRIPTS / "signaldeck_release.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)

SHA = "a" * 40


def write_repo(root: Path, versions: dict[str, str]) -> None:
    (root / "backend").mkdir()
    (root / "frontend").mkdir()
    (root / "VERSION").write_text(versions["root"] + "\n", encoding="utf-8")
    (root / "backend" / "VERSION").write_text(versions["root"] + "\n", encoding="utf-8")
    (root / "backend" / "pyproject.toml").write_text(
        f'[project]\nname = "signaldeck-backend"\nversion = "{versions["pyproject"]}"\n\n'
        '[tool.uv]\npackage = false\nversion = "not-this"\n',
        encoding="utf-8",
    )
    (root / "backend" / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "httpx"\nversion = "0.28.1"\n\n'
        f'[[package]]\nname = "signaldeck-backend"\nversion = "{versions["lock"]}"\n'
        'source = { virtual = "." }\n',
        encoding="utf-8",
    )
    (root / "frontend" / "VERSION").write_text(versions["root"] + "\n", encoding="utf-8")
    (root / "frontend" / "package.json").write_text(
        json.dumps({"name": "signaldeck-frontend", "version": versions["package"]}), encoding="utf-8"
    )


class ReleaseTests(unittest.TestCase):
    def test_parses_release_dry_run(self) -> None:
        output = "Release plan\n  Current version : 0.1.0\n  Target version  : 0.2.0\n  Root tag        : v0.2.0\n"
        self.assertEqual(
            MODULE.parse_release_plan(output),
            {"current_version": "0.1.0", "version": "0.2.0", "tag": "v0.2.0"},
        )
        with self.assertRaises(MODULE.ReleaseError):
            MODULE.parse_release_plan("Current version: 0.1.0\nTarget version: 0.2.0\nRoot tag: v9.0.0")

    def test_origin_slug(self) -> None:
        self.assertEqual(MODULE.parse_origin_slug("git@github.com:coachpo/signaldeck.git"), "coachpo/signaldeck")
        self.assertEqual(MODULE.parse_origin_slug("https://github.com/coachpo/signaldeck"), "coachpo/signaldeck")
        with self.assertRaises(MODULE.ReleaseError):
            MODULE.parse_origin_slug("https://example.com/coachpo/signaldeck.git")

    def test_workflow_gate_binds_release_sha_branch_and_tag(self) -> None:
        def run(name: str, branch: str, conclusion: str | None = "success", sha: str = SHA) -> dict[str, object]:
            return {
                "name": name,
                "event": "push",
                "head_sha": sha,
                "head_branch": branch,
                "status": "completed" if conclusion else "in_progress",
                "conclusion": conclusion,
                "id": 1,
                "html_url": "https://example.test",
            }

        payload = {"workflow_runs": [run("CI", "feature"), run("CI", "main"), run("Docker Images", "v0.2.0")]}
        workflows = MODULE.selected_workflows(payload, release_sha=SHA, tag="v0.2.0")
        self.assertEqual(MODULE.workflow_gate(workflows), "success")
        self.assertEqual(workflows["CI"]["head_branch"], "main")

        pending = {"workflow_runs": [run("CI", "main", None), run("Docker Images", "v0.2.0", None)]}
        self.assertEqual(MODULE.workflow_gate(MODULE.selected_workflows(pending, release_sha=SHA, tag="v0.2.0")), "pending")

        failed = {"workflow_runs": [run("CI", "main", "failure")]}
        self.assertEqual(MODULE.workflow_gate(MODULE.selected_workflows(failed, release_sha=SHA, tag="v0.2.0")), "failed")

        other_sha = {"workflow_runs": [run("CI", "main", sha="b" * 40), run("Docker Images", "v0.2.0")]}
        self.assertEqual(MODULE.workflow_gate(MODULE.selected_workflows(other_sha, release_sha=SHA, tag="v0.2.0")), "pending")

    def test_published_image_must_be_a_single_platform_release_manifest(self) -> None:
        good = {
            "manifest_digest": "sha256:" + "c" * 64,
            "manifest_media_type": "application/vnd.oci.image.manifest.v1+json",
            "os": "linux",
            "architecture": "arm64",
            "revision": SHA,
            "version": "0.2.0",
        }
        MODULE.validate_published_image(good, release_sha=SHA, version="0.2.0", host_arch="arm64")
        for field, value in (
            ("manifest_media_type", "application/vnd.oci.image.index.v1+json"),
            ("architecture", "amd64"),
            ("revision", "b" * 40),
            ("version", "main"),
            ("manifest_digest", "sha256:short"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(MODULE.ReleaseError):
                    MODULE.validate_published_image(
                        {**good, field: value}, release_sha=SHA, version="0.2.0", host_arch="arm64"
                    )
        self.assertEqual(MODULE.normalized_host_arch("aarch64\n"), "arm64")

    def test_version_surfaces_read_all_six_release_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_repo(root, {"root": "0.2.0", "pyproject": "0.2.0", "lock": "0.1.0", "package": "0.2.0"})
            surfaces = MODULE.version_surfaces(root)
        self.assertEqual(surfaces["backend/pyproject.toml"], "0.2.0")
        self.assertEqual(surfaces["backend/uv.lock"], "0.1.0")
        self.assertEqual(len(surfaces), 6)

    def test_manifest_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            MODULE.write_new(path, {"status": "published"})
            with self.assertRaises(MODULE.ReleaseError):
                MODULE.write_new(path, {"status": "published"})

    def test_execute_requires_the_exact_release_confirmation(self) -> None:
        plan = {"tag": "v0.2.0", "version": "0.2.0", "current_version": "0.1.0"}
        with patch.object(MODULE, "release_plan", return_value=plan), patch.object(MODULE, "run") as run:
            with self.assertRaises(MODULE.ReleaseError):
                MODULE.main(["execute", "--spec", "minor", "--confirm-release", "v0.3.0"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

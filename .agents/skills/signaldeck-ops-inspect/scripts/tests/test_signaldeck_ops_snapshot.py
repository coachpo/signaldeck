from __future__ import annotations

import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("signaldeck_ops_snapshot", SCRIPTS / "signaldeck_ops_snapshot.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)

IMAGE = "ghcr.io/coachpo/signaldeck:v0.2.0@sha256:" + "a" * 64


def entry(status: str = "running", health: str | None = None, image: str = IMAGE, exit_code: int = 0) -> dict[str, object]:
    return {"status": status, "health": health, "image_ref": image, "exit_code": exit_code}


def healthy_snapshot() -> dict[str, object]:
    return {
        "repository": {"version_surfaces": {"VERSION": "0.2.0", "backend/VERSION": "0.2.0"}},
        "deployment": {
            "topology": {"app_roles": ["app", "bootstrap", "dispatcher", "worker"]},
            "services": {
                "app": [entry(health="healthy")],
                "bootstrap": [entry(status="exited")],
                "dispatcher": [entry()],
                "worker": [entry()],
                "db": [entry(health="healthy", image="postgres:16")],
                "temporal": [entry(health="healthy", image="temporalio/server")],
                "notes-84c3ec46": [entry(image="ghcr.io/coachpo/signaldeck-notes:sha-1")],
            },
            "pinned_app_image": IMAGE,
            "http": {"ready": {"status": 200}},
        },
    }


class SnapshotCheckTests(unittest.TestCase):
    def test_healthy_pinned_deployment_passes(self) -> None:
        self.assertEqual(MODULE.check_snapshot(healthy_snapshot()), [])

    def test_pin_drift_is_reported(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["deployment"]["pinned_app_image"] = "ghcr.io/coachpo/signaldeck:sha-old"
        self.assertEqual(
            MODULE.check_snapshot(snapshot),
            [f"pinned application image ghcr.io/coachpo/signaldeck:sha-old differs from the running image"],
        )

    def test_unhealthy_split_or_failed_services_are_reported(self) -> None:
        snapshot = copy.deepcopy(healthy_snapshot())
        services = snapshot["deployment"]["services"]
        services["temporal"] = [entry(health="unhealthy", image="temporalio/server")]
        services["worker"] = [entry(image="ghcr.io/coachpo/signaldeck:sha-other")]
        services["notes-84c3ec46"] = [entry(status="exited", exit_code=3, image="n")]
        failures = MODULE.check_snapshot(snapshot)
        self.assertIn("temporal is running/unhealthy", failures)
        self.assertTrue(any(item.startswith("application roles run different images") for item in failures))
        self.assertIn("notes-84c3ec46 exited with 3", failures)

    def test_misaligned_repository_versions_fail(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["repository"]["version_surfaces"]["backend/VERSION"] = "0.1.0"
        self.assertIn("repository version surfaces are not aligned", MODULE.check_snapshot(snapshot))


class RepositoryTests(unittest.TestCase):
    def test_version_surfaces_parse_without_tomllib(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend").mkdir()
            (root / "frontend").mkdir()
            for path in ("VERSION", "backend/VERSION", "frontend/VERSION"):
                (root / path).write_text("0.2.0\n", encoding="utf-8")
            (root / "backend" / "pyproject.toml").write_text(
                '[project]\nname = "signaldeck-backend"\nversion = "0.2.0"\n\n[tool.black]\nversion = "x"\n',
                encoding="utf-8",
            )
            (root / "backend" / "uv.lock").write_text(
                '[[package]]\nname = "signaldeck-backend"\nversion = "0.2.0"\n', encoding="utf-8"
            )
            (root / "frontend" / "package.json").write_text('{"version": "0.2.0"}', encoding="utf-8")
            surfaces = MODULE.version_surfaces(root)
        self.assertEqual(set(surfaces.values()), {"0.2.0"})
        self.assertEqual(len(surfaces), 6)

    def test_origin_slug_is_sanitized(self) -> None:
        self.assertEqual(MODULE.parse_origin_slug("git@github.com:coachpo/signaldeck.git"), "coachpo/signaldeck")
        self.assertIsNone(MODULE.parse_origin_slug("https://token@example.com/repo"))

    def test_unreachable_host_is_a_limitation_and_fails_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(
            MODULE, "ssh_python", side_effect=MODULE.OpsError("remote operation failed (255): no route")
        ), patch.object(MODULE, "repository_snapshot", return_value=({"version_surfaces": {"VERSION": "1"}}, [])):
            output = Path(directory) / "snapshot.json"
            with redirect_stdout(io.StringIO()):
                code = MODULE.main(["--check", "--output", str(output)])
            snapshot = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertIsNone(snapshot["deployment"])
        self.assertEqual(snapshot["checks"], ["deployment snapshot unavailable"])
        self.assertTrue(snapshot["limitations"][0].startswith("deployment snapshot failed"))


if __name__ == "__main__":
    unittest.main()

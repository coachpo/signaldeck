from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("signaldeck_rollout", SCRIPTS / "signaldeck_rollout.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)

SHA = "0123456789abcdef" * 2 + "01234567"
NAMES = {"app": "signaldeck"}


def manifest() -> dict[str, object]:
    images = {}
    for index, (service, name) in enumerate(NAMES.items()):
        digest = "sha256:" + str(index) * 64
        repository = f"ghcr.io/coachpo/{name}"
        images[service] = {
            "repository": repository,
            "ref": f"{repository}:v0.2.0@{digest}",
            "manifest_digest": digest,
            "revision": SHA,
            "version": "0.2.0",
            "os": "linux",
            "architecture": "arm64",
        }
    return {
        "schema_version": 1,
        "status": "published",
        "repository": "coachpo/signaldeck",
        "version": "0.2.0",
        "tag": "v0.2.0",
        "release_sha": SHA,
        "images": images,
    }


def remote(program: str) -> dict[str, object]:
    namespace: dict[str, object] = {"__name__": "remote_under_test"}
    exec(compile(program, "remote", "exec"), namespace)
    return namespace


PREFLIGHT = {
    "topology": {
        "deploy_root": "/home/ubuntu/orange_work/curse",
        "deploy_name": "signaldeck",
        "app_repository": "ghcr.io/coachpo/signaldeck",
    },
    "previous_app_image": "ghcr.io/coachpo/signaldeck:sha-old@sha256:" + "e" * 64,
    # Plugin services run the application repository under their own pins, so the rollout
    # must leave their images unchanged.
    "service_images": {"db": "postgres:16", "finance-6198bd5c": "ghcr.io/coachpo/signaldeck:sha-" + "6" * 40},
}


class FakeHost:
    """Answers each remote program by its identity and records the order of stages."""

    def __init__(self, failing: str | None = None, compatible: bool = True) -> None:
        self.calls: list[str] = []
        self.payloads: dict[str, dict[str, object]] = {}
        self.failing = failing
        self.responses = {
            "preflight": PREFLIGHT,
            "schema": {"compatible": compatible, "tables": {}, "incompatible": {}, "unknown_tables": []},
            "plugins": {"plugins": {}},
            "read_backup": {"counts": {"signaldeck_core": {"public.platform_runs": 1}}},
            "post_deploy": {"health": {"version": "0.2.0"}},
            "pin": {"value": "v0.2.0@sha256:" + "0" * 64},
            "observe": {"status": "stable", "samples": 1},
            "stop": {"status": "stopped"},
        }

    def __call__(self, host: str, program: str, payload: dict[str, object], timeout: object = None) -> dict[str, object]:
        name = {
            MODULE.REMOTE_PREFLIGHT: "preflight",
            MODULE.REMOTE_SCHEMA_CHECK: "schema",
            MODULE.REMOTE_PLUGIN_COMPARE: "plugins",
            MODULE.REMOTE_READ_BACKUP: "read_backup",
            MODULE.REMOTE_POST_DEPLOY: "post_deploy",
            MODULE.REMOTE_PIN: "pin",
            MODULE.REMOTE_OBSERVE: "observe",
            MODULE.REMOTE_STOP: "stop",
        }[program]
        self.calls.append(name)
        self.payloads[name] = payload
        if name == self.failing:
            raise MODULE.OpsError(f"{name} failed")
        return self.responses[name]


def execute(host: FakeHost, directory: Path, *extra: str) -> tuple[int, dict[str, object], list[list[str]]]:
    manifest_path = directory / "release.json"
    manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
    evidence = directory / "evidence.json"
    backups: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        backups.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"manifest": "/b/x/manifest.json"}), stderr="")

    with patch.object(MODULE, "ssh_python", host), patch.object(
        MODULE, "revalidate_images", return_value={"images": {}}
    ), patch.object(MODULE, "run_deploy", return_value={"output_tail": "ok"}) as deploy, patch.object(
        MODULE.subprocess, "run", side_effect=fake_run
    ), redirect_stdout(io.StringIO()):
        code = MODULE.main(
            [
                "execute",
                "--manifest",
                str(manifest_path),
                "--confirm-rollout",
                "v0.2.0@" + SHA[:12],
                "--evidence",
                str(evidence),
                *extra,
            ]
        )
    if host.calls and "post_deploy" in host.calls:
        deploy.assert_called_once_with(
            "capy", "/home/ubuntu/orange_work/curse", "signaldeck", "v0.2.0@sha256:" + "0" * 64
        )
    return code, json.loads(evidence.read_text(encoding="utf-8")), backups


class ManifestTests(unittest.TestCase):
    def test_valid_manifest_and_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            path.write_text(json.dumps(manifest()), encoding="utf-8")
            loaded = MODULE.load_manifest(path)
        self.assertEqual(MODULE.rollout_token(loaded), "v0.2.0@" + SHA[:12])
        self.assertEqual(MODULE.image_refs(loaded)["app"], "ghcr.io/coachpo/signaldeck:v0.2.0@sha256:" + "0" * 64)

    def test_manifest_identity_drift_is_refused(self) -> None:
        cases = {
            "unpublished": lambda value: value.update(status="pending"),
            "mutable ref": lambda value: value["images"]["app"].update(ref="ghcr.io/coachpo/signaldeck:v0.2.0"),
            "other repository": lambda value: value["images"]["app"].update(repository="ghcr.io/else/signaldeck"),
            "revision": lambda value: value["images"]["app"].update(revision="f" * 40),
            "extra image": lambda value: value["images"].update(notes={}),
            "tag": lambda value: value.update(tag="v9.9.9"),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                value = manifest()
                mutate(value)
                path = Path(directory) / "release.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(MODULE.RolloutError):
                    MODULE.load_manifest(path)

    def test_version_spec_stays_inside_the_application_repository(self) -> None:
        self.assertEqual(
            MODULE.version_spec("ghcr.io/coachpo/signaldeck:v0.2.0@sha256:x", "ghcr.io/coachpo/signaldeck"),
            "v0.2.0@sha256:x",
        )
        with self.assertRaises(MODULE.RolloutError):
            MODULE.version_spec("ghcr.io/coachpo/signaldeck-notes:v0.2.0", "ghcr.io/coachpo/signaldeck")


class OrchestrationTests(unittest.TestCase):
    def test_plan_is_offline_and_execute_needs_the_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            path.write_text(json.dumps(manifest()), encoding="utf-8")
            host = FakeHost()
            with patch.object(MODULE, "ssh_python", host), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(MODULE.main(["plan", "--manifest", str(path)]), 0)
                with self.assertRaises(MODULE.RolloutError):
                    MODULE.main(["execute", "--manifest", str(path), "--confirm-rollout", "v0.2.0"])
        self.assertEqual(host.calls, [])
        self.assertEqual(json.loads(output.getvalue())["confirm_rollout"], "v0.2.0@" + SHA[:12])

    def test_successful_rollout_runs_every_gate_in_order(self) -> None:
        host = FakeHost()
        with tempfile.TemporaryDirectory() as directory:
            code, evidence, backups = execute(host, Path(directory), "--observe-seconds", "5")
        self.assertEqual(code, 0)
        self.assertEqual(evidence["status"], "complete")
        self.assertEqual(
            host.calls, ["preflight", "schema", "plugins", "read_backup", "post_deploy", "pin", "observe"]
        )
        self.assertEqual(evidence["stages"]["retention"], {"status": "not_requested"})
        self.assertEqual(len(backups), 1)
        self.assertIn("--confirm-backup", backups[0])
        self.assertEqual(host.payloads["observe"]["seconds"], 5)
        self.assertEqual(host.payloads["post_deploy"]["backup_counts"], {"signaldeck_core": {"public.platform_runs": 1}})
        self.assertEqual(host.payloads["post_deploy"]["service_images"], PREFLIGHT["service_images"])

    def test_incompatible_schema_stops_before_any_change(self) -> None:
        host = FakeHost(compatible=False)
        with tempfile.TemporaryDirectory() as directory:
            code, evidence, backups = execute(host, Path(directory))
        self.assertEqual(code, 1)
        self.assertEqual(evidence["failed_stage"], "schema compatibility")
        self.assertEqual(backups, [])
        self.assertNotIn("stop_gate", evidence)
        self.assertEqual(host.calls, ["preflight", "schema"])

    def test_failure_after_cutover_stops_the_application_and_reports_rollback(self) -> None:
        host = FakeHost(failing="post_deploy")
        with tempfile.TemporaryDirectory() as directory:
            code, evidence, _ = execute(host, Path(directory))
        self.assertEqual(code, 1)
        self.assertEqual(evidence["failed_stage"], "post-deploy gates")
        self.assertEqual(host.calls[-1], "stop")
        self.assertEqual(
            evidence["rollback_command"],
            "/home/ubuntu/orange_work/curse/deploy.sh start signaldeck --version sha-old@sha256:" + "e" * 64,
        )

    def test_plugin_comparison_failure_is_recorded_not_fatal(self) -> None:
        host = FakeHost(failing="plugins")
        with tempfile.TemporaryDirectory() as directory:
            code, evidence, _ = execute(host, Path(directory))
        self.assertEqual(code, 0)
        self.assertEqual(evidence["stages"]["plugin comparison"]["status"], "unavailable")


class RemoteProgramTests(unittest.TestCase):
    def test_schema_report_uses_the_last_output_line(self) -> None:
        program = remote(MODULE.REMOTE_SCHEMA_CHECK)
        report = program["schema_report_from"](
            "noise\n"
            + json.dumps(
                {
                    "compatible": False,
                    "tables": {
                        "platform_runs": {"status": "incompatible", "missing_columns": ["x"], "unmapped_required_columns": []},
                        "platform_new": {"status": "created_on_start"},
                    },
                    "unknown_tables": [],
                }
            )
        )
        self.assertFalse(report["compatible"])
        self.assertEqual(report["tables"], {"platform_runs": "incompatible", "platform_new": "created_on_start"})
        self.assertEqual(list(report["incompatible"]), ["platform_runs"])

    def test_remote_version_spec_and_plugin_applications(self) -> None:
        program = remote(MODULE.REMOTE_PLUGIN_COMPARE)
        self.assertEqual(program["version_spec"]("repo/app:v1@sha256:x", "repo/app"), "v1@sha256:x")
        applications = program["PLUGIN_APPLICATIONS"]
        self.assertEqual(
            set(applications), {"finance", "notes", "digital-oracle"}
        )
        self.assertEqual(applications["notes"], ("notes_plugin.main:create_app", "factory"))
        self.assertEqual(applications["digital-oracle"], ("oracle_plugin.main:app", "app"))
        compile(program["DESCRIBE"], "describe", "exec")


if __name__ == "__main__":
    unittest.main()

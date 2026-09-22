from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("signaldeck_ops_common", SCRIPTS / "signaldeck_ops_common.py")
COMMON = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(COMMON)


def remote(program: str) -> dict[str, object]:
    namespace: dict[str, object] = {"__name__": "remote_under_test"}
    exec(compile(program, "remote", "exec"), namespace)
    return namespace


def make_backup(root: Path, name: str, project: str = "signaldeck", created_at: str = "") -> Path:
    """Write a complete managed backup the remote validators accept."""
    backup = root / name
    backup.mkdir(parents=True)
    files = {
        "db-signaldeck_core.dump": b"dump",
        "db-signaldeck_core.list": b"list",
        "volume-signaldeck_target-core.tar.gz": b"archive",
        "config-backend.env": b"KEY=value\n",
    }
    for file_name, content in files.items():
        (backup / file_name).write_bytes(content)
    hashes = {file_name: hashlib.sha256(content).hexdigest() for file_name, content in files.items()}
    (backup / "SHA256SUMS").write_text(
        "".join(f"{hashes[file_name]}  {file_name}\n" for file_name in sorted(hashes)), encoding="utf-8"
    )
    (backup / "preflight.json").write_text("{}\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "status": "verified",
        "project": project,
        "created_at": created_at or name,
        "evidence_consistency": "quiesced_exact",
        "app_image_ref": "ghcr.io/example/signaldeck:v1.0.0@sha256:" + "a" * 64,
        "db_image_ref": "postgres:16@sha256:" + "b" * 64,
        "counts": {"signaldeck_core": {"public.platform_runs": 2}},
        "databases": [
            {
                "name": "signaldeck_core",
                "owner": "signaldeck_core",
                "size_bytes": 1,
                "dump": "db-signaldeck_core.dump",
                "list": "db-signaldeck_core.list",
            }
        ],
        "volumes": {
            "signaldeck_target-core": {
                "archive": "volume-signaldeck_target-core.tar.gz",
                "entries": 3,
                "size_bytes": 7,
            }
        },
        "configs": {"backend.env": "config-backend.env"},
        "artifacts": {
            file_name: {"path": file_name, "sha256": digest, "size_bytes": len(files[file_name])}
            for file_name, digest in hashes.items()
        },
        "preflight": {
            "path": "preflight.json",
            "sha256": hashlib.sha256(b"{}\n").hexdigest(),
        },
    }
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return backup


class LocalHelperTests(unittest.TestCase):
    def test_project_names_are_strict(self) -> None:
        self.assertEqual(COMMON.validate_project("signaldeck"), "signaldeck")
        for value in ("../signaldeck", "SignalDeck", "", "a b"):
            with self.assertRaises(COMMON.OpsError):
                COMMON.validate_project(value)

    def test_payload_encoding_has_no_shell_metacharacters(self) -> None:
        encoded = COMMON.encode_payload({"project": "signaldeck", "path": "/a b/'c'"})
        self.assertRegex(encoded, r"^[A-Za-z0-9_=\-]+$")

    def test_redaction_hides_secret_bearing_lines(self) -> None:
        text = "ok line\nDATABASE_URL=postgres://u:p@h/db\nAGENT_PLATFORM_ENCRYPTION_KEY=x"
        self.assertEqual(
            COMMON.redact(text),
            "ok line\n<redacted secret-bearing line>\n<redacted secret-bearing line>",
        )

    def test_ssh_python_rejects_secret_output_and_uses_one_program_on_stdin(self) -> None:
        completed = subprocess.CompletedProcess([], 0, stdout='{"password": "x"}', stderr="")
        with patch.object(COMMON.subprocess, "run", return_value=completed) as run:
            with self.assertRaises(COMMON.OpsError):
                COMMON.ssh_python("capy", "print(1)", {"project": "signaldeck"})
        argv = run.call_args.args[0]
        self.assertEqual(argv[:2], ["ssh", "-o"])
        self.assertEqual(argv[-3:-1], ["python3", "-"])
        self.assertEqual(run.call_args.kwargs["input"], "print(1)")

    def test_ssh_python_requires_a_json_object(self) -> None:
        for stdout in ("not json", "[1]"):
            completed = subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")
            with patch.object(COMMON.subprocess, "run", return_value=completed):
                with self.assertRaises(COMMON.OpsError):
                    COMMON.ssh_python("capy", "", {})


class RemoteHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.remote = remote(COMMON.REMOTE_COMMON)

    def test_image_references_split_into_repository_tag_and_digest(self) -> None:
        split = self.remote["split_image_ref"]
        self.assertEqual(
            split("ghcr.io/coachpo/signaldeck:v1.2.3@sha256:abc"),
            ("ghcr.io/coachpo/signaldeck", "v1.2.3", "sha256:abc"),
        )
        self.assertEqual(split("registry:5000/app"), ("registry:5000/app", None, None))
        self.assertEqual(split("postgres@sha256:abc"), ("postgres", None, "sha256:abc"))

    def test_env_value_replacement_touches_only_one_line(self) -> None:
        replace = self.remote["replace_env_value"]
        text = "A=1\nSIGNALDECK_VERSION=sha-old\nSECRET=keep\n"
        self.assertEqual(
            replace(text, "SIGNALDECK_VERSION", "v1.0.0@sha256:abc"),
            "A=1\nSIGNALDECK_VERSION=v1.0.0@sha256:abc\nSECRET=keep\n",
        )
        self.assertEqual(replace("A=1", "B", "2"), "A=1\nB=2\n")
        with self.assertRaises(RuntimeError):
            replace("B=1\nB=2\n", "B", "3")

    def test_env_pins_read_only_version_and_profile_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "backend.env"
            env_file.write_text(
                "SIGNALDECK_VERSION=sha-1\nSIGNALDECK_NOTES_VERSION='sha-2'\n"
                "COMPOSE_PROFILES=finance,notes\nDATABASE_URL=postgres://secret\n",
                encoding="utf-8",
            )
            pins = self.remote["env_pins"]({"env_file": env_file})
        self.assertEqual(
            pins,
            {
                "SIGNALDECK_VERSION": "sha-1",
                "SIGNALDECK_NOTES_VERSION": "sha-2",
                "COMPOSE_PROFILES": "finance,notes",
            },
        )

    def test_count_regressions_ignore_ephemeral_tables(self) -> None:
        regressions = self.remote["count_regressions"]
        before = {
            "signaldeck_core": {
                "public.platform_runs": 3,
                "public.platform_io_resource_permits": 5,
                "public.platform_evidence": 1,
            }
        }
        after = {
            "signaldeck_core": {
                "public.platform_runs": 2,
                "public.platform_io_resource_permits": 0,
            }
        }
        self.assertEqual(
            regressions(before, after),
            [
                {"database": "signaldeck_core", "table": "public.platform_runs", "before": 3, "after": 2},
                {"database": "signaldeck_core", "table": "public.platform_evidence", "before": 1, "after": None},
            ],
        )
        self.assertEqual(regressions(before, {"signaldeck_core": {**before["signaldeck_core"], "public.platform_runs": 4}}), [])

    def test_application_roles_are_the_services_the_version_variable_pins(self) -> None:
        repository = "ghcr.io/coachpo/signaldeck"
        release = f"{repository}:v0.3.0"
        # The plugin service runs the application repository under its own version variable.
        running = {
            **{name: release for name in ("app", "bootstrap", "dispatcher", "plugin-mounts", "worker")},
            "finance-6198bd5c": f"{repository}:sha-" + "6" * 40,
            "db": "postgres:16",
            "temporal": "temporalio/server",
        }

        def renderer(*followers: str):
            """Render the version variable into the followers' images; every other image is literal."""

            def render(argv: list[str], env: dict[str, str], **_: object) -> str:
                self.assertEqual(argv[-3:], ["config", "--format", "json"])
                images = {**running, "never-started": release}
                images.update({name: f"{repository}:{env['SIGNALDECK_VERSION']}" for name in followers})
                return json.dumps({"services": {name: {"image": image} for name, image in images.items()}})

            return render

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "signaldeck" / "compose.yml"
            config.parent.mkdir()
            config.write_text("services: {}\n", encoding="utf-8")
            self.remote["compose_rows"] = lambda: [{"Name": "signaldeck", "ConfigFiles": str(config)}]
            self.remote["project_containers"] = lambda project: {
                name: [{"Config": {"Image": image}}] for name, image in running.items()
            }
            self.remote["run"] = renderer("app", "bootstrap", "dispatcher", "plugin-mounts", "worker", "never-started")
            topology = self.remote["discover"]("signaldeck")
            self.assertEqual(topology["version_var"], "SIGNALDECK_VERSION")
            self.assertEqual(topology["app_repository"], repository)
            self.assertEqual(topology["app_roles"], ["app", "bootstrap", "dispatcher", "plugin-mounts", "worker"])

            self.remote["run"] = renderer("dispatcher", "worker")
            with self.assertRaisesRegex(RuntimeError, "does not follow SIGNALDECK_VERSION"):
                self.remote["discover"]("signaldeck")

    def test_engine_databases_are_not_counted(self) -> None:
        self.assertTrue(self.remote["is_engine_database"]("signaldeck_temporal_visibility"))
        self.assertFalse(self.remote["is_engine_database"]("signaldeck_core"))

    def test_validate_backup_accepts_complete_backups_only(self) -> None:
        validate = self.remote["validate_backup"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = make_backup(root, "20260101T000000Z-managed")
            self.assertEqual(validate(backup, "signaldeck")["status"], "verified")
            with self.assertRaises(ValueError):
                validate(backup, "another-project")

            (backup / "volume-signaldeck_target-core.tar.gz").write_bytes(b"tampered")
            self.assertEqual(validate(backup, "signaldeck", verify_hashes=False)["project"], "signaldeck")
            with self.assertRaises(ValueError):
                validate(backup, "signaldeck")

            incomplete = make_backup(root, "incomplete")
            (incomplete / ".incomplete").write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate(incomplete)

            linked = make_backup(root, "linked")
            target = linked / "db-signaldeck_core.dump"
            target.unlink()
            os.symlink(root / "incomplete" / "db-signaldeck_core.dump", target)
            with self.assertRaises(ValueError):
                validate(linked)

            extra = make_backup(root, "extra")
            manifest = json.loads((extra / "manifest.json").read_text(encoding="utf-8"))
            manifest["configs"]["compose.yml"] = "config-compose.yml"
            (extra / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate(extra)


if __name__ == "__main__":
    unittest.main()

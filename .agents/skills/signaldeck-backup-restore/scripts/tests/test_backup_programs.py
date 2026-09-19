from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ops_common import make_backup, remote  # noqa: E402


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


BACKUP = load("signaldeck_backup")
PRUNE = load("signaldeck_prune_backups")
RESTORE = load("signaldeck_restore_check")


class BackupTests(unittest.TestCase):
    def test_execute_requires_the_project_confirmation(self) -> None:
        with patch.object(BACKUP, "ssh_python") as ssh:
            with self.assertRaises(BACKUP.OpsError):
                BACKUP.main(["execute", "--project", "signaldeck"])
            with self.assertRaises(BACKUP.OpsError):
                BACKUP.main(["execute", "--confirm-backup", "other"])
        ssh.assert_not_called()

    def test_backup_root_override_must_be_absolute(self) -> None:
        with self.assertRaises(BACKUP.OpsError):
            BACKUP.main(["plan", "--backup-root", "relative/path"])

    def test_quiescing_stops_every_writer_but_keeps_postgres(self) -> None:
        program = remote(BACKUP.REMOTE_BACKUP)
        self.assertEqual(program["QUIESCE"], ("app", "dispatcher", "worker", "temporal"))
        self.assertNotIn("db", program["QUIESCE"])
        self.assertEqual(
            program["EXCLUDED_VOLUME_DESTINATIONS"],
            frozenset({"/var/lib/postgresql/data", "/data/uv-cache"}),
        )

    def test_the_manifest_is_written_after_verification(self) -> None:
        source = BACKUP.REMOTE_BACKUP
        self.assertLess(
            source.index("independent checksum verification failed"),
            source.index('write_atomic(backup_dir / "manifest.json"'),
        )
        self.assertLess(
            source.index('write_atomic(backup_dir / "manifest.json"'), source.index("incomplete.unlink()")
        )


class RetentionTests(unittest.TestCase):
    def test_keeps_the_newest_three_and_never_deletes_protected_or_unmanaged(self) -> None:
        program = remote(PRUNE.REMOTE_PRUNE)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(1, 6):
                make_backup(root, f"2026010{index}T000000Z-managed", created_at=f"2026-01-0{index}")
            (root / "unmanaged").mkdir()
            broken = make_backup(root, "20260109T000000Z-managed", created_at="2026-01-09")
            (broken / "db-signaldeck_core.dump").write_bytes(b"corrupt")
            protected = {str((root / "20260101T000000Z-managed").resolve())}

            managed = program["eligible_backups"](root, "signaldeck", protected)
            retained, candidates = program["select_candidates"](managed, 3)

        self.assertEqual(
            [item["path"].name for item in managed],
            [f"2026010{index}T000000Z-managed" for index in range(5, 0, -1)],
        )
        self.assertEqual(len(retained), 3)
        self.assertEqual([item["path"].name for item in candidates], ["20260102T000000Z-managed"])

    def test_execute_requires_the_exact_keep_three_token(self) -> None:
        with patch.object(PRUNE, "ssh_python") as ssh:
            with self.assertRaises(PRUNE.OpsError):
                PRUNE.main(["execute"])
            with self.assertRaises(PRUNE.OpsError):
                PRUNE.main(["plan", "--keep", "2"])
        ssh.assert_not_called()


class RestoreCheckTests(unittest.TestCase):
    def test_manifest_argument_must_be_an_absolute_manifest_path(self) -> None:
        for value in ("manifest.json", "/backups/x/SHA256SUMS"):
            with self.assertRaises(RESTORE.OpsError):
                RESTORE.main(["plan", "--manifest", value])

    def test_load_backup_validates_the_directory(self) -> None:
        program = remote(RESTORE.REMOTE_RESTORE_CHECK)
        with tempfile.TemporaryDirectory() as directory:
            backup = make_backup(Path(directory), "20260101T000000Z-managed")
            backup_dir, manifest = program["load_backup"](str(backup / "manifest.json"))
            self.assertEqual(backup_dir, backup)
            self.assertEqual(manifest["project"], "signaldeck")
            (backup / "config-backend.env").write_text("changed\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                program["load_backup"](str(backup / "manifest.json"))


if __name__ == "__main__":
    unittest.main()

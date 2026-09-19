"""Exercise private deployment configuration creation through its actual CLI."""

import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("create_env.py")
TEMPLATE = SCRIPT.with_name("production.env.example")
TAG = "sha-" + "a1" * 20
IMAGE = "ghcr.io/coachpo/signaldeck:v1.2.3@sha256:" + "c" * 64
SECRET_KEYS = (
    "POSTGRES_PASSWORD",
    "CORE_DB_PASSWORD",
    "FINANCE_DB_PASSWORD",
    "NOTES_DB_PASSWORD",
    "TEMPORAL_DB_PASSWORD",
    "AGENT_PLATFORM_ENCRYPTION_KEY",
)


class CreateEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.output = self.root / ".config/signaldeck/production.env"

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            env={**os.environ, "HOME": str(self.root)},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_default_creation_has_private_permissions_and_separate_secrets(self):
        result = self.run_cli("--plugin-tag", TAG, "--app-image", IMAGE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(self.output) + "\n")
        self.assertEqual(result.stderr, "")
        values = dict(
            line.split("=", 1)
            for line in self.output.read_text().splitlines()
            if line and not line.startswith("#")
        )
        secrets = [values[key] for key in SECRET_KEYS]
        self.assertEqual(len(set(secrets)), 6)
        for value in secrets:
            self.assertIsNotNone(re.fullmatch("[0-9a-f]{64}", value))
            self.assertNotIn(value, result.stdout + result.stderr)
        self.assertEqual(values["SIGNALDECK_PLUGIN_TAG"], TAG)
        self.assertEqual(values["SIGNALDECK_IMAGE"], IMAGE)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        for directory in (self.output.parent, self.output.parent.parent):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        replaced = {*SECRET_KEYS, "SIGNALDECK_PLUGIN_TAG", "SIGNALDECK_IMAGE"}
        for line in TEMPLATE.read_text().splitlines():
            if line.partition("=")[0] not in replaced:
                self.assertIn(line, self.output.read_text().splitlines())

    def test_custom_output_and_image_digest_preserve_existing_directory_mode(self):
        output = self.root / "chosen.env"
        self.root.chmod(0o755)
        image = "ghcr.io/coachpo/signaldeck@sha256:" + "b" * 64
        result = self.run_cli(
            "--plugin-tag", TAG, "--app-image", image, "--output", str(output)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o755)
        self.assertIn(f"SIGNALDECK_IMAGE={image}\n", output.read_text())
        self.assertFalse(self.output.exists())

    def test_existing_configuration_is_never_overwritten(self):
        self.output.parent.mkdir(parents=True)
        original = "existing private configuration\n"
        self.output.write_text(original)
        self.output.chmod(0o640)
        result = self.run_cli("--plugin-tag", TAG, "--app-image", IMAGE)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertNotIn(original.strip(), result.stderr)
        self.assertEqual(self.output.read_text(), original)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o640)

    def test_plugin_tag_requires_full_commit_sha(self):
        for tag in ("main", "v1.0.0", "sha-abcdef0", "sha-" + "g" * 40):
            with self.subTest(tag=tag):
                result = self.run_cli("--plugin-tag", tag, "--app-image", IMAGE)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())
        self.assertNotEqual(self.run_cli("--app-image", IMAGE).returncode, 0)

    def test_app_image_must_pin_a_release(self):
        for image in (
            None,
            "ghcr.io/coachpo/signaldeck",
            "ghcr.io/coachpo/signaldeck:latest",
            "ghcr.io/coachpo/signaldeck:1.2",
            "ghcr.io/coachpo/signaldeck:latest@sha256:" + "b" * 64,
        ):
            with self.subTest(image=image):
                args = () if image is None else ("--app-image", image)
                result = self.run_cli("--plugin-tag", TAG, *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("--app-image", result.stderr)
                self.assertFalse(self.output.exists())
        image = "ghcr.io/coachpo/signaldeck:v1.2.3"
        result = self.run_cli("--plugin-tag", TAG, "--app-image", image)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"SIGNALDECK_IMAGE={image}\n", self.output.read_text())

    def test_image_reference_cannot_inject_environment_lines(self):
        result = self.run_cli(
            "--plugin-tag", TAG, "--app-image", "image:tag\nCORE_DB_PASSWORD=injected"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()

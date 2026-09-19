from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from ssh_command import ssh_command  # noqa: E402


class SSHCommandTests(unittest.TestCase):
    def test_remote_arguments_are_one_shell_quoted_command(self) -> None:
        command = ssh_command(
            "capy",
            ["docker", "buildx", "imagetools", "inspect", "ghcr.io/example/signaldeck:v0.2.0", "--format", "{{json .Manifest}}"],
        )
        self.assertEqual(command[:4], ["ssh", "-o", "BatchMode=yes", "capy"])
        self.assertEqual(len(command), 5)
        self.assertIn("--format '{{json .Manifest}}'", command[4])

    def test_empty_values_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ssh_command("capy", ["deploy.sh", ""])


if __name__ == "__main__":
    unittest.main()

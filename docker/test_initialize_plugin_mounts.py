"""Protect retained plugin routing when application containers are recreated."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from initialize_plugin_mounts import merge_mounts


def registry(key="a", upstream="http://notes:8000"):
    return {
        "version": "signaldeck.pluginMounts/1",
        "mounts": [
            {
                "mountKey": key * 64,
                "pluginId": "example/notes",
                "artifactDigest": "sha256:" + key * 64,
                "upstream": upstream,
            }
        ],
    }


class MountInitializationTests(unittest.TestCase):
    def test_application_restart_keeps_exact_plugin_identity(self):
        previous = registry()
        self.assertEqual(merge_mounts(previous, registry()), previous)

    def test_new_release_keeps_old_route_with_an_independent_upstream(self):
        previous = registry()
        updated = merge_mounts(previous, registry("b", "http://notes-v2:8000"))
        self.assertEqual(updated["mounts"][0], previous["mounts"][0])
        self.assertEqual(len(updated["mounts"]), 2)

    def test_release_replacement_or_mount_rebinding_is_rejected(self):
        for replacement in (registry("b"), registry("a", "http://replacement:8000")):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                merge_mounts(registry(), replacement)

    def test_empty_selection_creates_registry_and_preserves_retained_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plugin-mounts.json"
            env = {
                "PATH": os.environ["PATH"],
                "SIGNALDECK_PLUGINS": "",
                "SIGNALDECK_PLUGIN_MOUNTS_FILE": str(path),
            }
            command = [
                sys.executable,
                str(Path(__file__).with_name("initialize_plugin_mounts.py")),
            ]
            subprocess.run(command, env=env, check=True, capture_output=True)
            self.assertEqual(json.loads(path.read_text())["mounts"], [])
            path.write_text(json.dumps(registry()))
            subprocess.run(command, env=env, check=True, capture_output=True)
            self.assertEqual(json.loads(path.read_text()), registry())


if __name__ == "__main__":
    unittest.main()

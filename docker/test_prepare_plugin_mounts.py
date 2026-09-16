"""Registry generations identify exact built releases and trigger app refresh."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RegistryTests(unittest.TestCase):
    def test_generation_revision_tracks_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            descriptors = root / "descriptors"
            descriptors.mkdir()
            script = Path(__file__).with_name("prepare_plugin_mounts.py")

            def generate():
                return subprocess.check_output(
                    [sys.executable, str(script), str(descriptors)], text=True
                ).strip()

            empty_revision = generate()
            digest = "a" * 64
            (descriptors / "finance.json").write_text(
                json.dumps(
                    {
                        "pluginId": "signaldeck/finance",
                        "artifactDigest": "sha256:" + digest,
                        "pageUrl": "/apps/" + digest + "/",
                    }
                )
            )
            revision = generate()
            self.assertNotEqual(empty_revision, revision)
            self.assertEqual(generate(), revision)
            registry = root / "plugin-mounts.json"
            self.assertEqual(
                hashlib.sha256(registry.read_bytes()).hexdigest(), revision
            )
            self.assertEqual(
                json.loads(registry.read_text())["mounts"][0]["mountKey"], digest
            )


if __name__ == "__main__":
    unittest.main()

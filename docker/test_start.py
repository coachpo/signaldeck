"""Launcher regression tests without starting or changing Docker services."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class LauncherTests(unittest.TestCase):
    def launch(self, plugins):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = root / "calls.jsonl"
            docker = root / "docker"
            docker.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ['TEST_DOCKER_CALLS'], 'a') as output:
    output.write(json.dumps(sys.argv[1:]) + '\\n')
if '--factories' in sys.argv:
    for name in os.environ['SIGNALDECK_PLUGINS'].split(','):
        if name:
            print(name, name + '_plugin.main:create_app')
elif 'plugin_runtime.describe' in sys.argv:
    # Docker streams stdin even when the plugin never reads it.
    sys.stdin.read()
    print('{}')
""")
            docker.chmod(0o755)
            env = {
                **os.environ,
                "PATH": str(root) + os.pathsep + os.environ["PATH"],
                "SIGNALDECK_PLUGINS": plugins,
                "SIGNALDECK_DATA_DIR": str(root / "data"),
                "TEST_DOCKER_CALLS": str(calls),
            }
            env.pop("SIGNALDECK_PLUGIN_MOUNTS_FILE", None)
            subprocess.run(
                [
                    "/bin/bash",
                    str(Path(__file__).parents[1] / "start.sh"),
                    "up",
                    "--detach",
                ],
                env=env,
                check=True,
                capture_output=True,
            )
            return [json.loads(line) for line in calls.read_text().splitlines()]

    def test_empty_plugins_complete_with_nounset(self):
        calls = self.launch("")
        self.assertEqual(calls[-1][-2:], ["up", "--detach"])

    def test_descriptor_stdin_does_not_consume_next_plugin(self):
        calls = self.launch("finance,notes")
        descriptions = [args[-1] for args in calls if "plugin_runtime.describe" in args]
        self.assertEqual(
            descriptions,
            ["finance_plugin.main:create_app", "notes_plugin.main:create_app"],
        )
        self.assertEqual(calls[-1][-2:], ["up", "--detach"])


if __name__ == "__main__":
    unittest.main()

"""Exercise application roles and child lifecycles with real stub processes."""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

STUB = r"""
import json
import os
from pathlib import Path
import signal
import sys
import time

name = Path(sys.argv[0]).name
args = sys.argv[1:]
def record(event):
    with open(os.environ["EVENTS"], "a") as stream:
        stream.write(json.dumps({"name": name, "args": args, "event": event,
                                 "pid": os.getpid()}) + "\n")

record("start")
if name == "envsubst":
    sys.stdout.write(sys.stdin.read())
    sys.exit(0)
if name == "python" and args[0] == "-c":
    sys.exit(int(os.environ.get("PREFLIGHT_STATUS", "0")))
if name == "python" and args[0] != "-m":
    sys.exit(0)
if name == "nginx" and args == ["-t"]:
    sys.exit(int(os.environ.get("NGINX_CONFIG_STATUS", "0")))

def stop(signum, frame):
    record("stopped")
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
record("ready")
if os.environ.get("EXIT_CHILD") == name:
    while not Path(os.environ["RELEASE"]).exists():
        time.sleep(0.01)
    sys.exit(int(os.environ["EXIT_STATUS"]))
while True:
    time.sleep(0.01)
"""


class EntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bash = shutil.which("bash")
        if not cls.bash or subprocess.check_output(
            [cls.bash, "-c", "echo ${BASH_VERSINFO[0]}"], text=True
        ).strip() in {"1", "2", "3"}:
            raise unittest.SkipTest("requires Bash >=4, as installed in the app image")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.events = self.root / "events.jsonl"
        self.release = self.root / "release"
        self.env = {
            **os.environ,
            "PATH": f"{self.root}:{os.environ['PATH']}",
            "EVENTS": str(self.events),
            "RELEASE": str(self.release),
        }
        source = Path(__file__).with_name("entrypoint.sh").read_text()
        # Remap only container filesystem locations; execute the unchanged shell logic.
        for prefix in ("/etc/nginx", "/run/nginx", "/opt/signaldeck"):
            source = source.replace(prefix, str(self.root / prefix.lstrip("/")))
        self.script = self.root / "entrypoint.sh"
        self.script.write_text(source)
        template = self.root / "etc/nginx/templates/default.conf.template"
        template.parent.mkdir(parents=True)
        template.write_text("server {}\n")
        (self.root / "etc/nginx/conf.d").mkdir()
        for name in (
            "python",
            "nginx",
            "uvicorn",
            "envsubst",
            "utility",
            "finance-python",
            "notes-python",
            "digital-oracle-python",
        ):
            stub = self.root / name
            stub.write_text(f"#!{sys.executable}\n{STUB}")
            stub.chmod(0o755)

    def recorded(self):
        if not self.events.exists():
            return []
        return [json.loads(line) for line in self.events.read_text().splitlines()]

    def launch(self, *args, **env):
        process = subprocess.Popen(
            [self.bash, str(self.script), *args], env={**self.env, **env}
        )

        def cleanup():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

        self.addCleanup(cleanup)
        return process

    def wait_ready(self, count):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            ready = [event for event in self.recorded() if event["event"] == "ready"]
            if len(ready) == count:
                return ready
            time.sleep(0.01)
        self.fail(f"expected {count} ready processes; got {self.recorded()}")

    def test_default_app_forwards_term_to_both_children(self):
        process = self.launch()
        ready = self.wait_ready(2)
        api = next(event for event in ready if event["name"] == "uvicorn")
        self.assertEqual(api["args"][1:5], ["--host", "127.0.0.1", "--port", "8000"])
        process.terminate()
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(
            {event["name"] for event in self.recorded() if event["event"] == "stopped"},
            {"uvicorn", "nginx"},
        )

    def test_app_forwards_interrupt_to_both_children(self):
        process = self.launch("app")
        self.wait_ready(2)
        process.send_signal(signal.SIGINT)
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(
            len([event for event in self.recorded() if event["event"] == "stopped"]), 2
        )

    def test_child_exit_fails_app_and_stops_peer(self):
        for child in ("uvicorn", "nginx"):
            for status in (0, 7):
                with self.subTest(child=child, status=status):
                    self.events.unlink(missing_ok=True)
                    self.release.unlink(missing_ok=True)
                    process = self.launch(
                        "app", EXIT_CHILD=child, EXIT_STATUS=str(status)
                    )
                    self.wait_ready(2)
                    self.release.touch()
                    self.assertEqual(process.wait(timeout=5), status or 1)
                    stopped = [
                        event["name"]
                        for event in self.recorded()
                        if event["event"] == "stopped"
                    ]
                    self.assertEqual(
                        stopped, ["nginx" if child == "uvicorn" else "uvicorn"]
                    )

    def test_configuration_failure_prevents_service_start(self):
        for role in ("app", "dispatcher", "worker"):
            with self.subTest(role=role):
                self.events.unlink(missing_ok=True)
                process = self.launch(role, PREFLIGHT_STATUS="4")
                self.assertEqual(process.wait(timeout=5), 4)
                self.assertEqual(len(self.recorded()), 1)

    def test_nginx_configuration_failure_prevents_children(self):
        process = self.launch("app", NGINX_CONFIG_STATUS="5")
        self.assertEqual(process.wait(timeout=5), 5)
        self.assertFalse(any(event["event"] == "ready" for event in self.recorded()))

    def test_execution_roles_replace_entrypoint_process(self):
        for role, module, extra in (
            ("dispatcher", "app.workers.command_dispatcher", []),
            ("worker", "app.workers.artifact_worker", ["--serve"]),
        ):
            with self.subTest(role=role):
                self.events.unlink(missing_ok=True)
                process = self.launch(role, "--example")
                ready = self.wait_ready(1)[0]
                self.assertEqual(ready["pid"], process.pid)
                self.assertEqual(ready["args"], ["-m", module, *extra, "--example"])
                process.terminate()
                self.assertEqual(process.wait(timeout=5), 0)

    def test_plugin_roles_run_their_own_environment_without_core_configuration(self):
        for role, module in (
            ("finance", "finance_plugin.main:create_app"),
            ("notes", "notes_plugin.main:create_app"),
            ("digital-oracle", "oracle_plugin.main:app"),
        ):
            with self.subTest(role=role):
                self.events.unlink(missing_ok=True)
                process = self.launch(role, PREFLIGHT_STATUS="4")
                ready = self.wait_ready(1)[0]
                self.assertEqual(ready["name"], f"{role}-python")
                self.assertEqual(ready["pid"], process.pid)
                self.assertEqual(ready["args"][:3], ["-m", "uvicorn", module])
                self.assertIn("--port", ready["args"])
                self.assertEqual(
                    ready["args"][ready["args"].index("--port") + 1], "8000"
                )
                self.assertEqual(
                    ready["args"][ready["args"].index("--host") + 1], "0.0.0.0"
                )
                process.terminate()
                self.assertEqual(process.wait(timeout=5), 0)
                self.assertFalse(
                    any(event["name"] == "python" for event in self.recorded())
                )

    def test_explicit_command_replaces_entrypoint_without_service_configuration(self):
        process = self.launch("utility", "--example", PREFLIGHT_STATUS="4")
        ready = self.wait_ready(1)[0]
        self.assertEqual(ready["pid"], process.pid)
        self.assertEqual(ready["args"], ["--example"])
        process.terminate()
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertFalse(any(event["name"] == "python" for event in self.recorded()))


if __name__ == "__main__":
    unittest.main()

"""Validate the self-hosted overlay without a daemon or local deployment secrets."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

DIRECTORY = Path(__file__).resolve().parent
REQUIRED_SECRETS = (
    "POSTGRES_PASSWORD",
    "CORE_DB_PASSWORD",
    "FINANCE_DB_PASSWORD",
    "NOTES_DB_PASSWORD",
    "TEMPORAL_DB_PASSWORD",
    "AGENT_PLATFORM_ENCRYPTION_KEY",
    "SIGNALDECK_API_TOKEN",
)


def compose_config(env_file):
    return subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(DIRECTORY / "compose.production.example.yml"),
            "-f",
            str(DIRECTORY / "compose.capy.yml"),
            "--profile",
            "*",
            "config",
            "--format",
            "json",
        ],
        env={key: os.environ[key] for key in ("PATH", "HOME")},
        capture_output=True,
        text=True,
        check=False,
    )


class CapyComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = (DIRECTORY / "capy.env.example").read_text()
        result = compose_config(DIRECTORY / "capy.env.example")
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.config = json.loads(result.stdout)
        cls.services = cls.config["services"]

    def test_only_frontend_publishes_a_loopback_port_and_no_service_builds(self):
        for name, service in self.services.items():
            with self.subTest(service=name):
                self.assertNotIn("build", service)
                if name != "frontend":
                    self.assertFalse(service.get("ports"))
        ports = self.services["frontend"]["ports"]
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0]["host_ip"], "127.0.0.1")
        self.assertEqual(ports[0]["target"], 8080)

    def test_temporal_server_and_schema_tools_use_one_pinned_release(self):
        images = [
            self.services[name]["image"]
            for name in ("temporal", "temporal-schema", "temporal-namespace")
        ]
        for name, image in zip(("server", "admin-tools", "admin-tools"), images):
            self.assertRegex(image, rf"^temporalio/{name}:[^@]+@sha256:[0-9a-f]{{64}}$")
        self.assertEqual(
            len({image.split(":", 1)[1].split("@")[0] for image in images}), 1
        )
        self.assertNotIn("start-dev", json.dumps(self.services))
        self.assertEqual(self.services["temporal"]["environment"]["DB"], "postgres12")
        db_volume = next(
            v for v in self.services["db"]["volumes"] if v["type"] == "volume"
        )
        self.assertEqual(db_volume["target"], "/var/lib/postgresql/data")
        self.assertIn(db_volume["source"], self.config["volumes"])

    def test_startup_waits_for_database_schema_namespace_and_api(self):
        dependencies = (
            ("temporal-schema", "db", "service_healthy"),
            ("temporal", "temporal-schema", "service_completed_successfully"),
            ("temporal-namespace", "temporal", "service_healthy"),
            ("dispatcher", "temporal-namespace", "service_completed_successfully"),
            ("worker", "temporal-namespace", "service_completed_successfully"),
            ("backend", "db", "service_healthy"),
            ("finance", "db", "service_healthy"),
            ("notes", "db", "service_healthy"),
            ("frontend", "backend", "service_healthy"),
            ("bootstrap", "backend", "service_healthy"),
        )
        for service, dependency, condition in dependencies:
            with self.subTest(service=service, dependency=dependency):
                self.assertEqual(
                    self.services[service]["depends_on"][dependency]["condition"],
                    condition,
                )

    def test_database_roles_and_databases_are_isolated(self):
        users, databases, passwords = [], [], []
        for name, key in (
            ("backend", "DATABASE_URL"),
            ("finance", "PLUGIN_DATABASE_URL"),
            ("notes", "PLUGIN_DATABASE_URL"),
        ):
            url = urlsplit(self.services[name]["environment"][key])
            self.assertEqual((url.hostname, url.port), ("db", 5432))
            users.append(url.username)
            databases.append(url.path.removeprefix("/"))
            passwords.append(url.password)
        temporal = self.services["temporal"]["environment"]
        users.append(temporal["POSTGRES_USER"])
        databases.extend((temporal["DBNAME"], temporal["VISIBILITY_DBNAME"]))
        passwords.append(temporal["POSTGRES_PWD"])
        bootstrap = self.services["db"]["environment"]
        users.append(bootstrap["POSTGRES_USER"])
        passwords.append(bootstrap["POSTGRES_PASSWORD"])
        for values in (users, databases, passwords):
            self.assertTrue(all(values))
            self.assertEqual(len(values), len(set(values)))
        self.assertEqual(
            self.services["temporal-schema"]["environment"]["SQL_PASSWORD"],
            temporal["POSTGRES_PWD"],
        )

    def test_bind_mounts_are_existing_read_only_files(self):
        for name, service in self.services.items():
            for volume in service.get("volumes", []):
                if volume["type"] != "bind":
                    continue
                with self.subTest(service=name, target=volume["target"]):
                    self.assertTrue(volume.get("read_only"))
                    self.assertFalse(
                        volume.get("bind", {}).get("create_host_path", False)
                    )
                    self.assertTrue(Path(volume["source"]).is_file(), volume["source"])

    def test_example_secrets_are_placeholders_and_missing_values_fail_early(self):
        lines = self.example.splitlines()
        values = dict(
            line.split("=", 1) for line in lines if line and not line.startswith("#")
        )
        for key in REQUIRED_SECRETS:
            self.assertTrue(values[key].startswith("replace-"), key)
            for missing in (True, False):
                with self.subTest(variable=key, missing=missing):
                    filtered = [
                        line for line in lines if not line.startswith(f"{key}=")
                    ]
                    if not missing:
                        filtered.append(f"{key}=")
                    with tempfile.TemporaryDirectory(
                        prefix="signaldeck-capy-config-"
                    ) as temp:
                        env_file = Path(temp) / "test.env"
                        env_file.write_text("\n".join(filtered) + "\n")
                        result = compose_config(env_file)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(key, result.stderr)


if __name__ == "__main__":
    unittest.main()

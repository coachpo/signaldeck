"""Validate the deployment entrypoint without a daemon or local secrets."""

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
)


def compose_config(env_file, **overrides):
    return subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(DIRECTORY / "compose.production.yml"),
            "config",
            "--format",
            "json",
        ],
        env={**{key: os.environ[key] for key in ("PATH", "HOME")}, **overrides},
        capture_output=True,
        text=True,
        check=False,
    )


class ProductionComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = (DIRECTORY / "production.env.example").read_text()
        result = compose_config(DIRECTORY / "production.env.example")
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.config = json.loads(result.stdout)
        cls.services = cls.config["services"]

    def test_one_published_image_without_builds_or_split_services(self):
        self.assertNotIn("backend", self.services)
        self.assertNotIn("frontend", self.services)
        self.assertEqual(
            self.services["app"]["image"],
            "ghcr.io/coachpo/signaldeck:replace-with-published-release-tag",
        )
        for name in ("finance", "notes", "digital-oracle"):
            self.assertEqual(
                self.services[name]["image"],
                "ghcr.io/coachpo/signaldeck:replace-with-published-sha-tag",
            )
        for name, service in self.services.items():
            with self.subTest(service=name):
                self.assertNotIn("build", service)
                if name != "app":
                    self.assertFalse(service.get("ports"))
        ports = self.services["app"]["ports"]
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0]["host_ip"], "127.0.0.1")
        self.assertEqual(ports[0]["target"], 8080)
        self.assertEqual(ports[0]["published"], "8089")

    def test_temporal_server_and_schema_tools_use_one_pinned_release(self):
        images = [
            self.services[name]["image"]
            for name in ("temporal", "temporal-schema", "temporal-namespace")
        ]
        for index, name in enumerate(("server", "admin-tools", "admin-tools")):
            image = images[index]
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
            ("app", "db", "service_healthy"),
            ("finance", "db", "service_healthy"),
            ("notes", "db", "service_healthy"),
            ("app", "plugin-mounts", "service_completed_successfully"),
            ("bootstrap", "app", "service_healthy"),
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
            ("app", "DATABASE_URL"),
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

    def test_example_secrets_are_placeholders_and_required_values_fail_early(self):
        lines = self.example.splitlines()
        values = dict(
            line.split("=", 1) for line in lines if line and not line.startswith("#")
        )
        for key in REQUIRED_SECRETS:
            self.assertTrue(values[key].startswith("replace-"), key)
        for key in (
            *REQUIRED_SECRETS,
            "SIGNALDECK_IMAGE",
            "SIGNALDECK_PLUGIN_IMAGE",
            "DATABASE_URL",
            "TEMPORAL_ADDRESS",
        ):
            for missing in (True, False):
                with self.subTest(variable=key, missing=missing):
                    filtered = [
                        line for line in lines if not line.startswith(f"{key}=")
                    ]
                    if not missing:
                        filtered.append(f"{key}=")
                    with tempfile.TemporaryDirectory(
                        prefix="signaldeck-production-config-"
                    ) as temp:
                        env_file = Path(temp) / "test.env"
                        env_file.write_text("\n".join(filtered) + "\n")
                        result = compose_config(env_file)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(key, result.stderr)

    def test_roles_share_application_image_and_core_storage(self):
        app = self.services["app"]
        for role in ("app", "dispatcher", "worker"):
            with self.subTest(role=role):
                service = self.services[role]
                self.assertEqual(service["image"], app["image"])
                self.assertEqual(service["command"], [role])
                self.assertEqual(service["volumes"], app["volumes"])
                self.assertEqual(
                    service["environment"]["SIGNALDECK_RUNTIME_MODE"], "production"
                )
                self.assertEqual(service["stop_grace_period"], "30s")
        for role in (
            "dispatcher",
            "worker",
            "plugin-mounts",
            "bootstrap",
            "finance",
            "notes",
            "digital-oracle",
        ):
            self.assertTrue(self.services[role]["healthcheck"]["disable"])
        for role in ("plugin-mounts", "bootstrap"):
            self.assertEqual(self.services[role]["image"], app["image"])
        # Plugin roles run the same image under an independently pinned reference,
        # so an application update never moves a registered plugin release.
        for role in ("finance", "notes", "digital-oracle"):
            service = self.services[role]
            self.assertEqual(service["command"], [role])
            self.assertEqual(service["image"].split(":", 1)[0], app["image"].split(":", 1)[0])
            self.assertNotEqual(service["image"], app["image"])
            self.assertFalse(service.get("volumes"))
        for variable in (
            "SIGNALDECK_ARTIFACT_DIR",
            "SIGNALDECK_CORE_ARTIFACT_DIR",
            "SIGNALDECK_CORE_ENV_DIR",
        ):
            directory = app["environment"][variable]
            volume = next(v for v in app["volumes"] if v["target"] == directory)
            self.assertEqual(volume["type"], "volume")
            self.assertIn(volume["source"], self.config["volumes"])

    def test_plugin_mounts_initializer_is_the_only_registry_writer(self):
        initializer = self.services["plugin-mounts"]
        writer = next(
            v for v in initializer["volumes"] if v["target"] == "/data/plugins"
        )
        self.assertEqual(writer["type"], "volume")
        self.assertFalse(writer.get("read_only"))
        for name in ("app", "dispatcher", "worker"):
            reader = next(
                v
                for v in self.services[name]["volumes"]
                if v["source"] == writer["source"]
            )
            self.assertTrue(reader["read_only"])
            self.assertEqual(reader["target"], "/etc/signaldeck/plugins")
        for name in ("finance", "notes", "digital-oracle"):
            dependency = initializer["depends_on"][name]
            self.assertFalse(dependency["required"])
            self.assertEqual(dependency["condition"], "service_started")

    def test_empty_plugin_selection_resolves_without_optional_services(self):
        result = compose_config(
            DIRECTORY / "production.env.example",
            COMPOSE_PROFILES="",
            SIGNALDECK_PLUGINS="",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        for name in ("finance", "notes", "digital-oracle"):
            self.assertNotIn(name, services)
        self.assertIn("app", services)
        self.assertEqual(
            services["plugin-mounts"]["environment"]["SIGNALDECK_PLUGINS"], ""
        )


if __name__ == "__main__":
    unittest.main()

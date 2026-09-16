"""Validate split deployment wiring without starting services or loading local secrets."""

import json
import os
import subprocess
import unittest
from pathlib import Path


class ProductionComposeTests(unittest.TestCase):
    def config(self, **overrides):
        env = {key: os.environ[key] for key in ("PATH", "HOME")}
        env.update(
            SIGNALDECK_BACKEND_IMAGE="signaldeck-backend:test",
            SIGNALDECK_FRONTEND_IMAGE="signaldeck-frontend:test",
            DATABASE_URL="postgresql+psycopg://test:test@db:5432/test",
            TEMPORAL_ADDRESS="temporal:7233",
            AGENT_PLATFORM_ENCRYPTION_KEY="isolated-test-key",
            SIGNALDECK_API_TOKEN="isolated-test-token",
        )
        env.update(overrides)
        return subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                os.devnull,
                "-f",
                str(Path(__file__).with_name("compose.production.example.yml")),
                "config",
                "--format",
                "json",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_split_roles_share_storage_and_use_explicit_images(self):
        result = self.config()
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        backend = services["backend"]
        for role in ("backend", "dispatcher", "worker"):
            service = services[role]
            self.assertEqual(service["image"], "signaldeck-backend:test")
            self.assertEqual(service["volumes"], backend["volumes"])
            self.assertNotIn("ports", service)
            self.assertEqual(
                service["environment"]["SIGNALDECK_RUNTIME_MODE"], "production"
            )
        frontend = services["frontend"]
        self.assertEqual(frontend["image"], "signaldeck-frontend:test")
        self.assertEqual(
            frontend["depends_on"]["backend"]["condition"], "service_healthy"
        )
        self.assertEqual(frontend["ports"][0]["host_ip"], "127.0.0.1")
        for service in (backend, frontend):
            mount = next(v for v in service["volumes"] if v["type"] == "bind")
            self.assertTrue(mount["read_only"])
            self.assertFalse(mount.get("bind", {}).get("create_host_path", False))
            self.assertTrue(Path(mount["source"]).is_file())

    def test_missing_required_values_fail_before_start(self):
        for name in (
            "SIGNALDECK_BACKEND_IMAGE",
            "SIGNALDECK_FRONTEND_IMAGE",
            "DATABASE_URL",
            "TEMPORAL_ADDRESS",
            "AGENT_PLATFORM_ENCRYPTION_KEY",
            "SIGNALDECK_API_TOKEN",
        ):
            with self.subTest(variable=name):
                self.assertNotEqual(self.config(**{name: ""}).returncode, 0)

    def test_ghcr_example_resolves_all_plugins_without_local_builds(self):
        directory = Path(__file__).parent
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(directory / "ghcr.env.example"),
                "-f",
                str(directory / "compose.production.example.yml"),
                "--profile",
                "finance",
                "--profile",
                "notes",
                "--profile",
                "digital-oracle",
                "config",
                "--format",
                "json",
            ],
            env={key: os.environ[key] for key in ("PATH", "HOME")},
            capture_output=True,
            text=True,
            check=True,
        )
        services = json.loads(result.stdout)["services"]
        for service in ("backend", "frontend", "finance", "notes", "digital-oracle"):
            self.assertEqual(
                services[service]["image"],
                f"ghcr.io/coachpo/signaldeck-{service}:replace-with-published-tag",
            )
            self.assertNotIn("build", services[service])
        self.assertEqual(services["frontend"]["ports"][0]["published"], "8089")
        urls = [
            services[s]["environment"][key]
            for s, key in (
                ("backend", "DATABASE_URL"),
                ("finance", "PLUGIN_DATABASE_URL"),
                ("notes", "PLUGIN_DATABASE_URL"),
            )
        ]
        self.assertEqual(len(set(urls)), 3)


if __name__ == "__main__":
    unittest.main()

"""Deployment input validation and fixed route boundaries."""

import unittest

from generate import render


class GatewayTests(unittest.TestCase):
    def registry(self, **values):
        mount = {
            "mountKey": "demo_v1",
            "pluginId": "third/example",
            "artifactDigest": "sha256:" + "a" * 64,
            "upstream": "http://absent-plugin:8000",
        }
        mount.update(values)
        return {"version": "signaldeck.pluginMounts/1", "mounts": [mount]}

    def test_fixed_mount_auth_and_late_resolution(self):
        config = render(self.registry(), "backend:8000")
        self.assertIn("resolver 127.0.0.11", config)
        self.assertIn('set $plugin_upstream "http://absent-plugin:8000"', config)
        self.assertIn("proxy_pass $plugin_upstream;", config)
        self.assertIn("location ^~ /_plugins/demo_v1/api/", config)
        self.assertEqual(config.count("auth_request /_plugin_auth;"), 1)
        self.assertIn('proxy_set_header Authorization "";', config)
        self.assertIn("location /_plugins/ { return 404; }", config)
        self.assertNotIn("/mcp", config)

    def test_optional_plugins_and_https(self):
        self.assertIn(
            "return 404",
            render(
                {"version": "signaldeck.pluginMounts/1", "mounts": []}, "backend:8000"
            ),
        )
        self.assertIn(
            "https://plugin.example",
            render(self.registry(upstream="https://plugin.example"), "backend:8000"),
        )

    def test_untrusted_upstream_and_duplicate_keys_rejected(self):
        for upstream in (
            "http://user:pass@host",
            "http://host/path",
            "http://host?x=y",
            "http://$request_host",
            "http://host; return 200;",
            "http://host_name:8000",
            "http://host:0",
            "http://host:99999",
        ):
            with self.subTest(upstream=upstream), self.assertRaises(ValueError):
                render(self.registry(upstream=upstream), "backend:8000")
        registry = self.registry()
        registry["mounts"] *= 2
        with self.assertRaises(ValueError):
            render(registry, "backend:8000")


if __name__ == "__main__":
    unittest.main()

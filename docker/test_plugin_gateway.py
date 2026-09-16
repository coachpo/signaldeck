"""Exercise real Nginx routing/auth with disposable mock services (requires Docker)."""

import importlib.util
import json
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def main():
    spec = importlib.util.spec_from_file_location(
        "gateway", Path(__file__).parents[1] / "frontend/gateway/generate.py"
    )
    gateway = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gateway)
    name = "signaldeck-gateway-test-" + uuid.uuid4().hex[:8]
    containers = []
    docker("network", "create", name)
    try:
        with tempfile.TemporaryDirectory(
            prefix=name, dir=Path(__file__).parents[1]
        ) as temp:
            root = Path(temp)
            (root / "server.py").write_text(
                """from http.server import BaseHTTPRequestHandler, HTTPServer
import json
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/plugin-auth':
            self.send_response(204 if self.headers.get('Authorization') == 'Bearer test-token' else 401)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({'path':self.path,'authorization':self.headers.get('Authorization'),'cookie':self.headers.get('Cookie')}).encode())
    do_POST = do_GET
HTTPServer(('0.0.0.0',8000),Handler).serve_forever()
"""
            )
            mock = docker(
                "run",
                "-d",
                "--network",
                name,
                "--network-alias",
                "mock",
                "-v",
                f"{root}:/test:ro",
                "python:3.13.13-slim",
                "python",
                "/test/server.py",
            )
            containers.append(mock)
            registry = {
                "version": "signaldeck.pluginMounts/1",
                "mounts": [
                    {
                        "mountKey": "third_v1",
                        "pluginId": "third/plugin",
                        "artifactDigest": "sha256:" + "a" * 64,
                        "upstream": "http://mock:8000",
                    },
                    {
                        "mountKey": "offline",
                        "pluginId": "third/offline",
                        "artifactDigest": "sha256:" + "b" * 64,
                        "upstream": "http://missing-plugin:8000",
                    },
                ],
            }
            (root / "default.conf").write_text(
                "server { listen 8080;\n"
                + gateway.render(registry, "mock:8000")
                + '\nlocation / { return 200 "shell"; }\n}'
            )
            nginx = docker(
                "run",
                "-d",
                "--network",
                name,
                "-p",
                "127.0.0.1::8080",
                "-v",
                f"{root}/default.conf:/etc/nginx/conf.d/default.conf:ro",
                "nginx:alpine",
            )
            containers.append(nginx)
            port = docker("port", nginx, "8080/tcp").split(":")[-1]
            base = "http://127.0.0.1:" + port

            def request(path, headers=None, method="GET"):
                try:
                    with urllib.request.urlopen(
                        urllib.request.Request(
                            base + path, headers=headers or {}, method=method
                        ),
                        timeout=8,
                    ) as response:
                        return response.status, response.read()
                except urllib.error.HTTPError as error:
                    return error.code, error.read()

            for attempt in range(30):
                try:
                    if request("/")[0] == 200:
                        break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.2)
            assert request("/_plugins/third_v1/")[0] == 200
            assert request("/_plugins/third_v1/api/notes")[0] == 401
            status, body = request(
                "/_plugins/third_v1/api/notes?item=42",
                {"Authorization": "Bearer test-token", "Cookie": "secret=hidden"},
            )
            assert status == 200, (status, body)
            assert json.loads(body) == {
                "path": "/api/notes?item=42",
                "authorization": None,
                "cookie": None,
            }
            status, body = request(
                "/_plugins/third_v1/api/a%20b?item=42",
                {"Authorization": "Bearer test-token"},
            )
            assert status == 200 and json.loads(body)["path"] == "/api/a%20b?item=42"
            assert request("/_plugins/third_v1/api/write", method="POST")[0] == 401
            assert (
                request(
                    "/_plugins/third_v1/api/write",
                    {"Authorization": "Bearer test-token"},
                    method="POST",
                )[0]
                == 200
            )
            for path in ("mcp/", "release", "internal", "api", "../release"):
                assert request("/_plugins/third_v1/" + path)[0] == 404, path
            assert request("/_plugins/unknown/")[0] == 404
            assert request("/_plugin_auth")[0] == 404
            assert request("/_plugins/offline/")[0] == 502
            assert request("/")[0] == 200
            print(
                "Gateway integration passed: auth, credential stripping, paths, absent plugin and shell isolation."
            )
    finally:
        for container in reversed(containers):
            docker("rm", "-f", container)
        docker("network", "rm", name)


if __name__ == "__main__":
    main()

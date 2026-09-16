"""Exercise real Nginx routing with disposable mock services (requires Docker)."""

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
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        self.send_response(200)
        self.send_header('Set-Cookie', 'plugin-cookie=hidden')
        self.end_headers()
        result = {
            'path': self.path,
            'authorization': self.headers.get('Authorization'),
            'cookie': self.headers.get('Cookie'),
        }
        if body:
            result['bodySize'] = len(body)
        self.wfile.write(json.dumps(result).encode())
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
                "--network-alias",
                "core-original",
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
                (Path(__file__).parents[1] / "docker/nginx.conf.template")
                .read_text()
                .replace("${PORT}", "8080")
                # Core is loopback in the app image. This external test double
                # uses a separate name so it cannot pin the dynamic plugin DNS pool.
                .replace("127.0.0.1:${BACKEND_PORT}", "core-original:8000")
            )
            (root / "plugin-locations.conf").write_text(gateway.render(registry))
            nginx = docker(
                "run",
                "-d",
                "--network",
                name,
                "-p",
                "127.0.0.1::8080",
                "-v",
                f"{root}/default.conf:/etc/nginx/conf.d/default.conf:ro",
                "-v",
                f"{root}/plugin-locations.conf:/etc/nginx/plugin-locations.conf:ro",
                "nginx:alpine",
            )
            containers.append(nginx)
            port = docker("port", nginx, "8080/tcp").split(":")[-1]
            base = "http://127.0.0.1:" + port

            def request(path, headers=None, method="GET", data=None):
                try:
                    with urllib.request.urlopen(
                        urllib.request.Request(
                            base + path, headers=headers or {}, method=method, data=data
                        ),
                        timeout=8,
                    ) as response:
                        return response.status, response.read()
                except urllib.error.HTTPError as error:
                    return error.code, error.read()

            status, body = 0, b""
            for _ in range(30):
                try:
                    status, body = request("/api/probe?item=original")
                    if status == 200:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.2)
            assert status == 200, (status, body)
            assert json.loads(body) == {
                "path": "/api/probe?item=original",
                "authorization": None,
                "cookie": None,
            }
            assert request("/_plugins/third_v1/")[0] == 200
            assert request("/_plugins/third_v1/api/notes")[0] == 200
            with urllib.request.urlopen(base + "/_plugins/third_v1/") as response:
                assert response.headers.get("Set-Cookie") is None
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
            )
            assert status == 200 and json.loads(body)["path"] == "/api/a%20b?item=42"
            assert request("/_plugins/third_v1/api/write", method="POST")[0] == 200
            for path in ("", "ui/page", "assets/app.js"):
                assert request("/_plugins/third_v1/" + path, method="POST")[0] == 403
            upload = b"x" * (1024 * 1024 + 1)
            status, body = request(
                "/_plugins/third_v1/api/upload",
                method="POST",
                data=upload,
            )
            assert status == 200, (status, body)
            assert json.loads(body) == {
                "path": "/api/upload",
                "authorization": None,
                "cookie": None,
                "bodySize": len(upload),
            }
            for path in ("mcp/", "release", "internal", "api", "../release"):
                assert request("/_plugins/third_v1/" + path)[0] == 404, path
            assert request("/_plugins/unknown/")[0] == 404
            assert request("/_plugins/offline/")[0] == 502
            assert request("/")[0] == 200
            # Attach the replacement before detaching the old endpoint so Docker
            # must assign a different IP; keep Nginx running throughout the change.
            replacement = docker(
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
            containers.append(replacement)
            address = "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"
            assert docker("inspect", "-f", address, mock) != docker(
                "inspect", "-f", address, replacement
            )
            docker("network", "disconnect", name, mock)
            deadline = time.monotonic() + 30
            while True:
                try:
                    status, body = request(
                        "/_plugins/third_v1/api/notes?item=replacement"
                    )
                    if status == 200:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                assert (
                    time.monotonic() < deadline
                ), "Gateway did not resolve the replacement backend"
                time.sleep(0.2)
            assert json.loads(body) == {
                "path": "/api/notes?item=replacement",
                "authorization": None,
                "cookie": None,
            }
            print(
                "Gateway integration passed: anonymous Core/plugin API, credential stripping, "
                "paths, static methods, uploads, absent plugin, shell isolation "
                "and plugin DNS refresh."
            )
    finally:
        for container in reversed(containers):
            docker("rm", "-f", container)
        docker("network", "rm", name)


if __name__ == "__main__":
    main()

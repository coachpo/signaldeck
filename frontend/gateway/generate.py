"""Render fixed trusted plugin locations; never derive upstreams from requests."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


def render(registry, backend):
    if (
        set(registry) != {"version", "mounts"}
        or registry["version"] != "signaldeck.pluginMounts/1"
    ):
        raise ValueError("Invalid plugin mount registry version")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+:[0-9]{1,5}", backend):
        raise ValueError("Invalid backend upstream")
    lines = [
        "resolver 127.0.0.11 valid=10s ipv6=off;",
        """location = /_plugin_auth {
    internal;
    proxy_pass http://BACKEND/api/plugin-auth;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header Authorization $http_authorization;
}""".replace("BACKEND", backend),
    ]
    seen = set()
    releases = set()
    for mount in registry["mounts"]:
        if set(mount) != {"mountKey", "pluginId", "artifactDigest", "upstream"}:
            raise ValueError("Invalid plugin mount fields")
        key, upstream = mount["mountKey"], mount["upstream"]
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key)
            or key in seen
        ):
            raise ValueError("Invalid or repeated plugin mount key")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", mount["artifactDigest"]):
            raise ValueError("Invalid artifact digest")
        if not isinstance(mount["pluginId"], str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.-]*", mount["pluginId"]
        ):
            raise ValueError("Invalid plugin identity")
        if not isinstance(upstream, str) or not re.fullmatch(
            r"https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?", upstream
        ):
            raise ValueError("Invalid plugin upstream")
        port = urlsplit(upstream).port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("Invalid upstream port")
        identity = (mount["pluginId"], mount["artifactDigest"])
        if identity in releases:
            raise ValueError("Repeated plugin release")
        releases.add(identity)
        seen.add(key)
        prefix = "/_plugins/" + key
        lines.append(f"location = {prefix}/api {{ return 404; }}")
        for path in ("/", "/ui/", "/assets/", "/api/"):
            match = "= " if path == "/" else "^~ "
            auth = (
                "auth_request /_plugin_auth;"
                if path == "/api/"
                else "limit_except GET HEAD { deny all; }"
            )
            lines.append(f"""location {match}{prefix}{path} {{
    {auth}
    set $plugin_upstream "{upstream}";
    rewrite ^{prefix}(/.*)$ $1 break;
    proxy_pass $plugin_upstream;
    proxy_set_header Host $proxy_host;
    proxy_ssl_server_name on;
    proxy_set_header Authorization "";
    proxy_set_header Cookie "";
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_hide_header Set-Cookie;
    proxy_redirect off;
    proxy_connect_timeout 3s;
}}""")
    lines.append("location /_plugins/ { return 404; }")
    return "\n\n".join(lines) + "\n"


if __name__ == "__main__":
    source = os.environ.get("SIGNALDECK_PLUGIN_MOUNTS_FILE")
    registry = (
        json.loads(Path(source).read_text())
        if source
        else {"version": "signaldeck.pluginMounts/1", "mounts": []}
    )
    Path("/etc/nginx/plugin-locations.conf").write_text(
        render(registry, os.environ.get("BACKEND_UPSTREAM", "127.0.0.1:8000"))
    )

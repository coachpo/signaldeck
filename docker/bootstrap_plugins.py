"""Install missing local plugin descriptors through Core's public HTTP boundary."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def request(url: str, *, payload: object | None = None, core: bool = False) -> dict:
    headers = {"Content-Type": "application/json"}
    if core and os.environ.get("SIGNALDECK_API_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["SIGNALDECK_API_TOKEN"]
    body = json.dumps(payload).encode() if payload is not None else None
    with urllib.request.urlopen(
        urllib.request.Request(url, data=body, headers=headers), timeout=5
    ) as response:
        return json.loads(response.read(4 * 1024 * 1024))


def main() -> None:
    api = os.environ.get("SIGNALDECK_API_URL", "http://app:8000/api").rstrip("/")
    enabled = set(os.environ.get("SIGNALDECK_PLUGINS", "").split(","))
    defaults = json.loads(Path(__file__).with_name("plugin-defaults.json").read_text())
    try:
        installed = {
            item["pluginId"]: item for item in request(api + "/plugins", core=True)["items"]
        }
        resources = {item["resourceId"] for item in request(api + "/resources", core=True)["items"]}
    except Exception:
        print("Plugin bootstrap skipped: Core API unavailable; existing configuration retained")
        return
    for plugin in defaults:
        if plugin["profile"] not in enabled:
            continue
        previous = installed.get(plugin["pluginId"])
        refresh = os.environ.get("SIGNALDECK_BOOTSTRAP_REFRESH") == "1"
        release = previous["release"] if previous else None
        if previous and not refresh:
            print("Existing plugin configuration retained: " + plugin["pluginId"])
        else:
            release = None
            for attempt in range(10):
                try:
                    release = request(plugin["descriptorUrl"])
                    break
                except Exception:
                    if attempt < 9:
                        time.sleep(1)
            if release is None:
                print("Plugin unavailable; Core remains usable: " + plugin["pluginId"])
                continue

        try:
            if release["pluginId"] != plugin["pluginId"]:
                raise ValueError("Plugin descriptor identity mismatch")
            if previous is None or refresh:
                request(
                    api + "/plugins",
                    payload={
                        "release": release,
                        "enabled": previous["enabled"] if previous else True,
                    },
                    core=True,
                )
            for resource in plugin["resources"]:
                if resource["resourceId"] not in resources:
                    request(api + "/resources", payload=resource, core=True)
                    resources.add(resource["resourceId"])
            print("Local plugin defaults ready: " + plugin["pluginId"])
        except Exception:
            print("Plugin configuration rejected: " + plugin["pluginId"])


if __name__ == "__main__":
    main()

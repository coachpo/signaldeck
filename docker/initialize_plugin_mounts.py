"""Prepare retained plugin mounts before the application gateway starts."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bootstrap_plugins import request


def merge_mounts(previous, current):
    mounts = {item["mountKey"]: item for item in previous["mounts"]}
    for item in current["mounts"]:
        if item["mountKey"] in mounts and mounts[item["mountKey"]] != item:
            raise ValueError(
                "A retained plugin mount cannot change identity or upstream"
            )
        for old in mounts.values():
            if old["upstream"] == item["upstream"] and old != item:
                raise ValueError(
                    "A new plugin release requires an independent upstream"
                )
        mounts[item["mountKey"]] = item
    return {"version": "signaldeck.pluginMounts/1", "mounts": list(mounts.values())}


def main():
    target = Path(os.environ["SIGNALDECK_PLUGIN_MOUNTS_FILE"])
    target.parent.mkdir(parents=True, exist_ok=True)
    defaults = json.loads(Path(__file__).with_name("plugin-defaults.json").read_text())
    enabled = {
        p.strip()
        for p in os.environ.get("SIGNALDECK_PLUGINS", "").split(",")
        if p.strip()
    }
    if enabled - {plugin["profile"] for plugin in defaults}:
        raise ValueError("Unknown deployment plugin profile")
    previous = (
        json.loads(target.read_text())
        if target.exists()
        else {
            "version": "signaldeck.pluginMounts/1",
            "mounts": [],
        }
    )
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        releases = Path(temporary) / "releases"
        releases.mkdir()
        for plugin in defaults:
            if plugin["profile"] not in enabled or not plugin.get("descriptorFactory"):
                continue
            for attempt in range(10):
                try:
                    release = request(plugin["descriptorUrl"])
                    break
                except (OSError, ValueError):
                    if attempt < 9:
                        time.sleep(1)
            else:
                print(
                    "Plugin unavailable; retained mounts preserved: "
                    + plugin["profile"]
                )
                continue
            (releases / (plugin["profile"] + ".json")).write_text(json.dumps(release))
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("prepare_plugin_mounts.py")),
                str(releases),
            ],
            check=True,
            capture_output=True,
        )
        current = json.loads((Path(temporary) / "plugin-mounts.json").read_text())
        result = merge_mounts(previous, current)
        updated = Path(temporary) / "merged.json"
        updated.write_text(json.dumps(result, indent=2) + "\n")
        updated.replace(target)


if __name__ == "__main__":
    main()

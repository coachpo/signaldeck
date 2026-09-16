"""Bind local built artifacts to explicit deployment upstreams before startup."""

import hashlib
import json
import sys
from pathlib import Path


def main():
    defaults = json.loads(Path(__file__).with_name("plugin-defaults.json").read_text())
    if sys.argv[1] == "--factories":
        enabled = set(sys.argv[2].split(","))
        for plugin in defaults:
            if plugin["profile"] in enabled and plugin.get("descriptorFactory"):
                print(plugin["profile"], plugin["descriptorFactory"])
        return
    if sys.argv[1] == "--revision":
        print(hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest())
        return
    directory = Path(sys.argv[1])
    mounts = []
    for plugin in defaults:
        source = directory / (plugin["profile"] + ".json")
        if not source.exists():
            continue
        release = json.loads(source.read_text())
        if release["pluginId"] != plugin["pluginId"]:
            raise ValueError("Built descriptor does not match deployment identity")
        key = release["artifactDigest"].removeprefix("sha256:")
        if "/apps/" + key + "/" not in release.get("pageUrl", ""):
            raise ValueError("Built descriptor does not expose its immutable mount")
        mounts.append(
            {
                "mountKey": key,
                "pluginId": release["pluginId"],
                "artifactDigest": release["artifactDigest"],
                "upstream": plugin["uiUpstream"],
            }
        )
    target = directory.parent / "plugin-mounts.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"version": "signaldeck.pluginMounts/1", "mounts": mounts}, indent=2)
        + "\n"
    )
    temporary.replace(target)
    print(hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()

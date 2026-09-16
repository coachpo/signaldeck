"""Print a built plugin descriptor without starting workers or database lifecycle."""

import asyncio
import json
import sys
from importlib import import_module


def main():
    module, factory = sys.argv[1].split(":", 1)
    app = getattr(import_module(module), factory)()
    for route in app.routes:
        if getattr(route, "path", None) == "/release":
            value = route.endpoint()
            if asyncio.iscoroutine(value):
                value = asyncio.run(value)
            print(json.dumps(value, separators=(",", ":")))
            return
    raise RuntimeError("Plugin does not expose a release descriptor")


if __name__ == "__main__":
    main()

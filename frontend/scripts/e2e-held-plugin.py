"""A separately owned MCP write for browser observations of uncertain effects."""

import json
import os
import sys
from pathlib import Path

import uvicorn

root = Path(__file__).resolve().parents[2]
state, port, identity = sys.argv[1:]
sys.path[:0] = [str(root / "plugins/runtime"), str(root / "backend/tests/fixtures")]
from plugin_runtime.server import obj, release, tool

schema = obj(
    {"value": {"type": "integer"}, "delay": {"type": "number"}, "tag": {"type": "string"}},
    ("value", "delay", "tag"),
)
plugin_id = f"example/ux-fault-{identity}"
binding = release(
    plugin_id,
    "1.0.0",
    f"http://127.0.0.1:{port}/mcp/",
    [tool(plugin_id, "write", schema, schema, "Controlled independent write", write=True)],
    [root / "plugins/runtime", root / "backend/tests/fixtures", root / "frontend/scripts"],
    configuration={"cooperativeCancellation": False},
)
binding["supportsOperationDeduplication"] = False
Path(state, "release.json").write_text(json.dumps(binding))
os.environ["HELD_PLUGIN_STATE"] = state
os.environ["HELD_PLUGIN_COOPERATIVE"] = "0"
from held_plugin import app

uvicorn.run(app, host="127.0.0.1", port=int(port), access_log=False, timeout_graceful_shutdown=2)

"""Stop only a service spawned by this harness, using its nonce-bound control file."""

import json
import os
import sys
from pathlib import Path

action = sys.argv[1] if len(sys.argv) == 2 else ""
if action not in {"stop_notes", "stop_temporal", "stop_provider"}:
    raise SystemExit("Usage: control.py stop_notes|stop_temporal|stop_provider")
state = json.loads(
    (
        Path(os.environ.get("GOAL_REAL_OUTPUT_DIR", Path(__file__).parent)) / "control.json"
    ).read_text()
)
Path(state["requestPath"]).write_text(json.dumps({"nonce": state["nonce"], "action": action}))
print("Requested " + action + " for this harness only")

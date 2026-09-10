"""Real Notes service with explicit, file-controlled fault injection at its boundary.

No model responses are mocked. write_reply_lost commits the actual note and journal
before losing the tool reply, allowing genuine write-unknown protection to be checked.
"""

import importlib
import json
import os
import sys
import threading
import time
from pathlib import Path

import uvicorn

OUT = Path(os.environ.get("GOAL_REAL_OUTPUT_DIR", Path(__file__).parent)).resolve()
ROOT = Path(os.environ["GOAL_WORKSPACE"]).resolve()
for name in ("runtime", "notes"):
    sys.path.insert(0, str(ROOT / "plugins" / name))
notes = importlib.import_module("notes_plugin.main")

original_application = notes.application
lock = threading.Lock()


def instrumented_application(binding, execute, query, **kwargs):
    def observed_execute(name, arguments, context):
        fault_path = OUT / "notes-fault.json"
        mode = (
            json.loads(fault_path.read_text()).get("mode", "off") if fault_path.exists() else "off"
        )
        event = {
            "timestamp": time.time(),
            "toolId": name,
            "operationId": context["operationId"],
            "mode": mode,
        }
        if mode == "read_error" and name == "example/notes/search":
            event["fault"] = "injected_read_failure_before_query"
            with lock, (OUT / "notes-observations.jsonl").open("a") as f:
                f.write(json.dumps(event) + "\n")
            raise RuntimeError("owned_read_fault")
        result = execute(name, arguments, context)
        event["sourceNoteIds"] = result.get("sourceNoteIds", [])
        event["noteId"] = result.get("id")
        if (
            mode in {"write_reply_lost", "write_reply_lost_recoverable"}
            and name == "example/notes/create"
        ):
            event["fault"] = "injected_reply_failure_after_committed_write"
        with lock, (OUT / "notes-observations.jsonl").open("a") as f:
            f.write(json.dumps(event) + "\n")
        if event.get("fault"):
            raise RuntimeError("owned_reply_lost_after_commit")
        return result

    def observed_query(operation_id, *args):
        fault_path = OUT / "notes-fault.json"
        mode = (
            json.loads(fault_path.read_text()).get("mode", "off") if fault_path.exists() else "off"
        )
        if mode == "write_reply_lost":
            with lock, (OUT / "notes-observations.jsonl").open("a") as f:
                f.write(
                    json.dumps(
                        {
                            "timestamp": time.time(),
                            "operationId": operation_id,
                            "fault": "injected_operation_query_unavailable_after_committed_write",
                        }
                    )
                    + "\n"
                )
            raise RuntimeError("owned_operation_query_unavailable")
        return query(operation_id, *args)

    return original_application(binding, observed_execute, observed_query, **kwargs)


notes.application = instrumented_application
app = notes.create_app()
uvicorn.run(
    app, host="127.0.0.1", port=int(os.environ.get("OWNED_NOTES_PORT", "21082")), access_log=False
)

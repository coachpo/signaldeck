"""Delay genuine upstream bytes to reproduce a lost model reply on an owned port."""

import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OUT = Path(os.environ["GOAL_REAL_OUTPUT_DIR"])
base = json.loads((Path.home() / ".pi/agent/models.json").read_text())["providers"]["prism"][
    "baseUrl"
].rstrip("/")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        assert self.path == "/v1/chat/completions"
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        sent = json.loads(raw)
        started = time.time()
        status = None
        usage = None
        reasons = []
        try:
            req = urllib.request.Request(
                base + "/chat/completions",
                data=raw,
                headers={
                    k: v
                    for k, v in self.headers.items()
                    if k.lower() in {"authorization", "content-type"}
                },
                method="POST",
            )
            try:
                response = urllib.request.urlopen(req, timeout=120)
            except urllib.error.HTTPError as error:
                response = error
            status = response.status
            body = response.read()
            received = json.loads(body)
            usage = received.get("usage")
            reasons = [c.get("finish_reason") for c in received.get("choices", [])]
            time.sleep(3)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (OSError, ValueError):
            pass
        finally:
            event = {
                "requestStartedAt": started,
                "finishedAt": time.time(),
                "max_tokens": sent.get("max_tokens"),
                "httpStatus": status,
                "usage": usage,
                "finishReasons": reasons,
                "fault": "genuine_response_delayed_at_least_3_seconds",
            }
            with (OUT / "model-timeout-relay.jsonl").open("a") as f:
                f.write(json.dumps(event) + "\n")


print("Owned slow real-provider relay 4375 ready", flush=True)
ThreadingHTTPServer(("127.0.0.1", 4375), Handler).serve_forever()

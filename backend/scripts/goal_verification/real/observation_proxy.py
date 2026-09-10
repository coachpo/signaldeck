"""Same-origin test UI and byte-preserving real-provider relay with numeric usage logs."""

import hashlib
import json
import os
import pathlib
import threading
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

OUT = pathlib.Path(os.environ.get("GOAL_REAL_OUTPUT_DIR", pathlib.Path(__file__).parent)).resolve()
WEB = pathlib.Path(os.environ["GOAL_WORKSPACE"]) / "frontend/dist"
PROVIDER = json.loads((pathlib.Path.home() / ".pi/agent/models.json").read_text())["providers"][
    "prism"
]["baseUrl"].rstrip("/")
LOCK = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, *args):
        pass

    def forward(self):
        provider = self.path.startswith("/provider/v1/")
        target = (
            PROVIDER + self.path[len("/provider/v1") :]
            if provider
            else "http://127.0.0.1:8301" + self.path
        )
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() in ("authorization", "content-type", "accept")
        }
        req = urllib.request.Request(
            target, data=raw if raw else None, headers=headers, method=self.command
        )
        started = time.monotonic()
        request_started_at = time.time()
        try:
            response = urllib.request.urlopen(req, timeout=180)
            status = response.status
        except urllib.error.HTTPError as e:
            response = e
            status = e.code
        body = response.read()
        if provider:
            try:
                sent = json.loads(raw)
                received = json.loads(body)
                event = {
                    "timestamp": time.time(),
                    "requestStartedAt": request_started_at,
                    "httpStatus": status,
                    "modelRequested": sent.get("model"),
                    "maxTokens": sent.get("max_tokens"),
                    "maxCompletionTokens": sent.get("max_completion_tokens"),
                    "requestSha256": hashlib.sha256(raw).hexdigest(),
                    "responseSha256": hashlib.sha256(body).hexdigest(),
                    "visibleContent": [
                        (c.get("message") or {}).get("content") for c in received.get("choices", [])
                    ],
                    "toolCalls": [
                        (c.get("message") or {}).get("tool_calls")
                        for c in received.get("choices", [])
                    ],
                    "toolCount": len(sent.get("tools", [])),
                    "responseId": received.get("id"),
                    "modelReturned": received.get("model"),
                    "usage": received.get("usage"),
                    "finishReasons": [c.get("finish_reason") for c in received.get("choices", [])],
                    "elapsedSeconds": round(time.monotonic() - started, 3),
                }
                if status >= 400:
                    event["safeErrorCode"] = (received.get("error") or {}).get("code")
                with LOCK:
                    with (OUT / "provider-observations.jsonl").open("a") as f:
                        f.write(json.dumps(event, ensure_ascii=False) + "\n")
            except (ValueError, TypeError):
                pass
        self.send_response(status)
        self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith(("/api/", "/provider/v1/")):
            return self.forward()
        if not pathlib.Path(self.translate_path(self.path)).is_file() and not self.path.startswith(
            "/assets/"
        ):
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        self.forward()

    def do_PATCH(self):
        self.forward()

    def do_PUT(self):
        self.forward()

    def do_DELETE(self):
        self.forward()


print("Owned same-origin UI/observation relay listening at 127.0.0.1:4374", flush=True)
ThreadingHTTPServer(("127.0.0.1", 4374), Handler).serve_forever()

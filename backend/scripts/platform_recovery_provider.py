"""Local HTTP model fixture for the product recovery verification script."""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class RecoveryProvider:
    def __init__(self, events: Path) -> None:
        self.events = events
        self.release = threading.Event()
        self.gated = threading.Event()
        self.lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_POST(self) -> None:
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                response = owner.respond(request, self.headers.get("Authorization", ""))
                encoded = json.dumps(response).encode()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1"

    def respond(self, request: dict[str, Any], authorization: str) -> dict[str, Any]:
        user = next(message for message in request["messages"] if message["role"] == "user")
        prompt = json.loads(user["content"])
        tag = prompt["input"]["tag"]
        returns = [m for m in request["messages"] if m["role"] == "tool"]
        round_number = len(returns)
        with self.lock:
            with self.events.open("a") as stream:
                stream.write(
                    json.dumps(
                        {
                            "tag": tag,
                            "round": round_number,
                            "model": request["model"],
                            "instructions": prompt["instructions"],
                            "credentialFingerprint": hashlib.sha256(
                                authorization.encode()
                            ).hexdigest(),
                        }
                    )
                    + "\n"
                )
        if tag == "retained" and round_number == 1:
            self.gated.set()
            if not self.release.wait(240):
                raise TimeoutError("recovery fixture gate expired")
        if round_number < 2:
            wanted = "title" if round_number == 0 else "query"
            selected = next(
                item["function"]["name"]
                for item in request["tools"]
                if wanted in item["function"]["parameters"]["properties"]
            )
            arguments = (
                {"title": f"agent-{tag}", "text": f"body-{tag}:" + "x" * 70000}
                if round_number == 0
                else {"query": f"agent-{tag}", "limit": 1}
            )
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call-{round_number}",
                        "type": "function",
                        "function": {"name": selected, "arguments": json.dumps(arguments)},
                    }
                ],
            }
            finish = "tool_calls"
        else:
            search_result = json.loads(returns[-1]["content"])
            message = {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "note": search_result["notes"][0],
                        "modelId": request["model"],
                        "instructions": prompt["instructions"],
                    }
                ),
            }
            finish = "stop"
        return {
            "id": f"fake-{tag}-{round_number}",
            "object": "chat.completion",
            "created": 1700000000,
            "model": request["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 20, "total_tokens": 40},
        }

    def stop(self) -> None:
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

"""Notes source navigation uses the real read-only service and isolated records."""

import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from tests.test_independent_plugins import invocation, notes_app


def test_notes_sources_in_browser(database_url):
    subprocess.run(
        ["pnpm", "build:plugin-ui"],
        cwd=Path(__file__).resolve().parents[2] / "frontend",
        check=True,
        timeout=120,
    )
    app = notes_app(database_url)
    create = "example/notes/create"
    with TestClient(app):
        app.state.execute(
            create,
            {
                "title": "访谈原始记录",
                "text": "用户原文 inputs.my_code 保持原样。",
                "sourceKind": "original",
            },
            invocation(create, "browser-original-internal-identity"),
        )
        app.state.execute(
            create,
            {
                "title": "访谈要点整理",
                "text": "整理结果，待结合原文核对。",
                "sourceKind": "derived",
                "sourceNoteIds": ["browser-original-internal-identity"],
            },
            invocation(create, "browser-derived-internal-identity"),
        )
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.02)
            assert server.started
            subprocess.run(
                [
                    "node",
                    str(Path(__file__).resolve().parents[2] / "plugins/notes/tests/browser.mjs"),
                ],
                env={**os.environ, "NOTES_TEST_URL": f"http://127.0.0.1:{port}/"},
                check=True,
                timeout=90,
            )
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()
    app.state.engine.dispose()

"""Run the three built plugin images against disposable local PostgreSQL databases."""

import asyncio
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path("backend/tests").resolve()))
sys.path.insert(0, str(Path("backend").resolve()))
from conftest import _get_base_database_url  # noqa: E402

base = _get_base_database_url()
if base.host not in {"localhost", "127.0.0.1", "::1"}:
    raise ValueError("Image smoke requires local PostgreSQL")
admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
containers = []
databases = []


def free():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(name):
    port = free()
    url = f"http://127.0.0.1:{port}"
    uid = uuid4().hex
    env = {**os.environ, "PLUGIN_ENDPOINT": url + "/mcp/"}
    if name != "digital-oracle":
        db = "plugin_image_" + uid
        databases.append(db)
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{db}"'))
        env["PLUGIN_DATABASE_URL"] = base.set(
            database=db, host="host.docker.internal"
        ).render_as_string(hide_password=False)
    container = "sd-plugin-smoke-" + uid
    containers.append(container)
    args = [
        "docker",
        "run",
        "-d",
        "--name",
        container,
        "-p",
        f"127.0.0.1:{port}:8000",
        "-e",
        "PLUGIN_ENDPOINT",
    ]
    if name != "digital-oracle":
        args += ["-e", "PLUGIN_DATABASE_URL"]
    subprocess.run(
        args + [f"signaldeck-{name}:sd-target-001"], env=env, check=True, stdout=subprocess.DEVNULL
    )
    for _ in range(160):
        try:
            response = httpx.get(url + "/release", timeout=0.3)
            if response.status_code == 200:
                return url, response.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(name + " container did not become ready")


async def mcp_write(url, tool_id, arguments, resources):
    async with streamable_http_client(url + "/mcp/") as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            identity = (await session.list_tools()).meta["signaldeck/release"]
            ctx = {
                "runId": str(uuid4()),
                "nodeId": "node",
                "invocationId": str(uuid4()),
                "operationId": str(uuid4()),
                "deadline": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
                "toolGrants": [tool_id],
                "resourceGrants": list(resources),
                "resourceBindings": resources,
            }
            meta = {"signaldeck/release": identity, "signaldeck/context": ctx}
            first = await session.call_tool(tool_id, arguments, meta=meta)
            assert not first.isError, first
            query = await session.call_tool(
                "signaldeck/operations/query", {"operationId": ctx["operationId"]}, meta=meta
            )
            assert query.structuredContent["output"] == first.structuredContent


try:
    for name in ["finance", "digital-oracle", "notes"]:
        url, release = start(name)
        if name == "finance":
            assert httpx.get(url + "/").status_code == 200
            template = httpx.post(
                url + "/api/templates", json={"name": "Smoke", "content": "Hello {{inputs.name}}"}
            )
            assert template.status_code == 201, template.text
            result = httpx.post(
                url + "/api/reports/compile/" + str(template.json()["id"]),
                json={"inputs": {"name": "image"}},
            )
            assert result.status_code == 201, result.text
            assert result.json()["content"] == "Hello image"
            asyncio.run(
                mcp_write(
                    url,
                    "signaldeck/finance/reports_create",
                    {"name": "Agent output", "content": "Image confirmed"},
                    {},
                )
            )
        if name == "notes":
            asyncio.run(
                mcp_write(
                    url,
                    "example/notes/create",
                    {"title": "Image smoke", "text": "Locked dependencies"},
                    {"notes-workspace": {"collection": "image-test"}},
                )
            )
        print(name, "image smoke passed", release["releaseId"], len(release["tools"]))
finally:
    for name in containers:
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, check=False)
    with admin.connect() as c:
        for db in databases:
            c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
    admin.dispose()

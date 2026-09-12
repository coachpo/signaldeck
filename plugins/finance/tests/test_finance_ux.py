"""Finance-owned HTTP contracts; use a UUID database, never application records."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from finance_plugin.main import create_app
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture
def finance_client(request):
    if request.node.name == "test_actual_browser_flow":
        subprocess.run(
            ["pnpm", "build:plugin-ui"],
            cwd=Path(__file__).resolve().parents[3] / "frontend",
            check=True,
            timeout=120,
        )
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        port = (
            subprocess.check_output(
                ["docker", "port", "signaldeck-target-test-postgres", "5432/tcp"],
                text=True,
            )
            .strip()
            .rsplit(":", 1)[-1]
        )
        raw = f"postgresql+psycopg://signaldeck:signaldeck@127.0.0.1:{port}/postgres"
    base = make_url(raw)
    name = "signaldeck_test_finance_ux_" + uuid4().hex
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    app = create_app(base.set(database=name).render_as_string(hide_password=False))
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.state.engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def test_history_search_filters_sort_and_pages(finance_client):
    client = finance_client
    for index in range(19):
        response = client.post(
            "/api/reports",
            json={
                "name": f"Report {index:02d}",
                "content": f"Evidence {index} literal_%",
                "metadata": {"tags": ["review"], "analysis": {"ticker": "MSFT"}},
            },
        )
        assert response.status_code == 201
    params = {
        "q": "literal_%",
        "ticker": "MSFT",
        "tag": "review",
        "sort": "name",
        "limit": 15,
    }
    page1 = client.get("/api/reports", params=params).json()
    page2 = client.get("/api/reports", params={**params, "offset": 15}).json()
    assert len(page1) == 15 and len(page2) == 4
    assert page2[-1]["name"] == "Report 18"
    assert not ({r["id"] for r in page1} & {r["id"] for r in page2})
    assert client.get("/api/reports", params={"q": "Evidence 18"}).json()[0]["name"] == "Report 18"
    assert client.get("/api/reports", params={"source": "agent"}).json() == []
    assert client.get("/api/reports", params={"sort": "invalid"}).status_code == 422


def test_preview_optional_fields_download_and_changed_reference(finance_client):
    client = finance_client
    content = (
        "<!-- input: company | 公司名称 | required -->\n"
        "<!-- input: notes | 补充说明 | optional -->\n"
        "# {{inputs.company}}\n{{inputs.notes}}\n{{reports.latest.content}}"
    )
    client.post("/api/reports", json={"name": "Source", "content": "Original evidence"})
    template = client.post("/api/templates", json={"name": "研究格式", "content": content}).json()
    inputs = {"company": "Example", "notes": ""}
    compiled = client.post(
        "/api/templates/compile", json={"content": content, "inputs": inputs}
    ).json()["compiled"]
    assert "input:" not in compiled and "Original evidence" in compiled
    payload = {
        "inputs": inputs,
        "expectedContent": content,
        "expectedCompiled": compiled,
    }
    report = client.post(f"/api/reports/compile/{template['id']}", json=payload)
    assert report.status_code == 201
    slug = report.json()["slug"]
    assert client.get(f"/api/reports/by-id/{report.json()['id']}").json()["slug"] == slug
    assert client.get(f"/api/reports/{slug}/download").text == compiled
    assert client.get(f"/?report={slug}").status_code == 200
    client.post("/api/reports", json={"name": "New evidence", "content": "Changed"})
    conflict = client.post(f"/api/reports/compile/{template['id']}", json=payload)
    assert conflict.status_code == 409 and conflict.json()["code"] == "preview_changed"
    client.patch(f"/api/templates/{template['id']}", json={"content": "Different format"})
    assert client.post(f"/api/reports/compile/{template['id']}", json=payload).status_code == 409
    assert client.get(f"/api/reports/{slug}").json()["content"] == compiled


def test_compiler_diagnostics_and_missing_report(finance_client):
    client = finance_client
    result = client.post(
        "/api/templates/compile",
        json={
            "content": "{{inputs.company}} {{unknown.field}} {{reports.latest.no_such_field}}",
            "inputs": {},
        },
    ).json()["compiled"]
    assert "[Missing input: company]" in result and "[Unknown root: unknown]" in result
    assert client.get("/api/reports/missing").status_code == 404


def test_business_labels_preserve_report_identity(finance_client):
    client = finance_client
    report = client.app.state.execute(
        "signaldeck/finance/reports_create",
        {"name": "季度研究", "content": "保持原始正文。"},
        {
            "operationId": "business-label-operation",
            "runId": "internal-run",
            "nodeId": "internal-node",
            "invocationId": "internal-invocation",
        },
    )
    assert report["name"].startswith("季度研究_")
    tree = client.get("/api/templates/placeholders").json()
    assert tree["reports"][0]["name"] == report["name"]
    assert tree["reports"][0]["label"] == "季度研究"
    content = "<!-- input: field_1 | 本周进展 | required -->\n{{inputs}}\n{{reports.latest.name}}"
    compiled = client.post(
        "/api/templates/compile",
        json={"content": content, "inputs": {"field_1": "已完成"}},
    ).json()["compiled"]
    assert "本周进展: 已完成" in compiled
    assert "季度研究" in compiled and report["name"] not in compiled
    assert client.get(f"/api/reports/{report['slug']}").json()["content"] == "保持原始正文。"


def test_actual_browser_flow(finance_client):
    """Actual Finance HTTP + PostgreSQL, not route mocks or synthetic UI responses."""
    import socket
    import threading
    import time
    from pathlib import Path

    import uvicorn

    client = finance_client
    client.post(
        "/api/templates",
        json={
            "name": "研究格式",
            "content": (
                "<!-- input: company | 公司名称 | required -->\n"
                "<!-- input: notes | 补充说明 | optional -->\n"
                "# {{inputs.company}}\n{{inputs.notes}}"
            ),
        },
    )
    for index in range(19):
        client.post(
            "/api/reports",
            json={"name": f"Report {index:02d}", "content": "Historical evidence"},
        )
    client.app.state.execute(
        "signaldeck/finance/reports_create",
        {"name": "任务生成结果", "content": "任务保存的原始正文。"},
        {
            "operationId": "browser-private-operation",
            "runId": "browser-private-run",
            "nodeId": "browser-private-node",
            "invocationId": "browser-private-invocation",
        },
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(client.app, log_level="error", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.02)
        assert server.started
        subprocess.run(
            ["node", str(Path(__file__).with_name("browser.mjs"))],
            env={**os.environ, "FINANCE_TEST_URL": f"http://127.0.0.1:{port}/"},
            check=True,
            timeout=120,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()

"""Independent artifacts use real PostgreSQL and MCP; no external market/model calls."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "finance", "digital_oracle", "notes"):
    sys.path.insert(0, str(PLUGINS / directory))

from finance_plugin.main import create_app as finance_app  # noqa: E402
from finance_plugin.providers.quote_provider import DeterministicQuoteProvider  # noqa: E402
from notes_plugin.main import create_app as notes_app  # noqa: E402
from oracle_plugin.main import app as oracle_app  # noqa: E402


def descriptor(app):
    return next(
        route for route in app.routes if getattr(route, "path", "") == "/release"
    ).endpoint()


def invocation(tool_id, operation_id=None):
    return {
        "runId": str(uuid4()),
        "nodeId": "node",
        "invocationId": str(uuid4()),
        "operationId": operation_id or str(uuid4()),
        "deadline": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
        "toolGrants": [tool_id],
        "resourceGrants": (
            ["notes-workspace"]
            if tool_id.startswith("example/notes/")
            else ["finance-market-data"] if "finance/market_" in tool_id else []
        ),
        "resourceBindings": (
            {"notes-workspace": {"collection": "research"}}
            if tool_id.startswith("example/notes/")
            else (
                {"finance-market-data": {"allowedSymbols": ["MSFT"]}}
                if "finance/market_" in tool_id
                else {}
            )
        ),
    }


def test_artifacts_import_without_core():
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            str(PLUGINS / p) for p in ("runtime", "finance", "digital_oracle", "notes")
        ),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import finance_plugin.main, oracle_plugin.main, notes_plugin.main; "
            'assert not any(k == "app" or k.startswith("app.") for k in sys.modules)',
        ],
        cwd=PLUGINS,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_published_contracts_use_supported_closed_dialect():
    from app.domain.tool_contracts import PluginRelease

    for app in [
        finance_app("postgresql+psycopg://localhost/unused"),
        oracle_app,
        notes_app("postgresql+psycopg://localhost/unused"),
    ]:
        release = PluginRelease.model_validate(descriptor(app))
        assert len(release.tools) >= 2
        assert release.artifact_digest.startswith("sha256:")


def test_finance_owned_crud_compile_upload_and_immutable_agent_reports(database_url):
    app = finance_app(database_url, DeterministicQuoteProvider())
    with TestClient(app) as client:
        created = client.post(
            "/api/templates", json={"name": "Daily", "content": "Research: {{inputs.symbol}}"}
        ).json()
        assert client.get("/api/templates").json()[0]["id"] == created["id"]
        assert (
            client.post(
                f"/api/templates/{created['id']}/compile", json={"inputs": {"symbol": "MSFT"}}
            ).json()["compiled"]
            == "Research: MSFT"
        )
        compiled = client.post(
            f"/api/reports/compile/{created['id']}", json={"inputs": {"symbol": "MSFT"}}
        )
        assert compiled.status_code == 201
        assert compiled.json()["source"] == "compiled"
        slug = compiled.json()["slug"]
        assert client.get(f"/api/reports/{slug}/download").text == "Research: MSFT"
        assert (
            client.patch(f"/api/reports/{slug}", json={"content": "Revised research"}).status_code
            == 200
        )
        uploaded = client.post(
            "/api/reports/upload", files={"file": ("review.md", b"# Review", "text/markdown")}
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["source"] == "uploaded"
        forged = client.post(
            "/api/reports",
            json={"name": "Forge", "content": "x", "metadata": {"createdBy": {"type": "agent"}}},
        )
        assert forged.status_code == 422
        tool = "signaldeck/finance/reports_create"
        context = invocation(tool)
        report = app.state.execute(
            tool, {"name": "Agent report", "content": "Confirmed evidence"}, context
        )
        assert report["metadata"]["createdBy"]["operationId"] == context["operationId"]
        from jsonschema import Draft202012Validator

        contract = next(item for item in descriptor(app)["tools"] if item["toolId"] == tool)
        Draft202012Validator(contract["outputSchema"]).validate(report)
        assert (
            app.state.execute(
                tool, {"name": "Agent report", "content": "Confirmed evidence"}, context
            )
            == report
        )
        assert (
            client.patch(
                "/api/reports/" + report["slug"], json={"content": "overwrite"}
            ).status_code
            == 409
        )
        assert client.delete("/api/reports/" + report["slug"]).status_code == 409
        assert client.delete(f"/api/reports/{slug}").status_code == 204
        assert client.delete(f"/api/templates/{created['id']}").status_code == 204
        assert client.get("/").status_code == 200
        missing = client.get("/api/missing")
        assert missing.status_code == 404
        assert set(missing.json()) == {"code", "message", "details"}
    app.state.engine.dispose()


def test_finance_market_output_has_strings_and_no_implicit_cross_run_fallback(database_url):
    from finance_plugin.providers.quote_provider import QuoteProviderError

    class Provider(DeterministicQuoteProvider):
        fail = False

        def fetch_quote(self, symbol):
            if self.fail:
                raise QuoteProviderError("credential-sensitive-upstream-message")
            return super().fetch_quote(symbol)

    provider = Provider()
    app = finance_app(database_url, provider)
    tool = "signaldeck/finance/market_data_quote_lookup"
    with TestClient(app):
        result = app.state.execute(tool, {"symbols": ["MSFT"]}, invocation(tool))
        assert isinstance(result["quotes"][0]["price"], str)
        ohlcv = "signaldeck/finance/market_data_ohlcv_lookup"
        candles = app.state.execute(
            ohlcv,
            {
                "symbols": ["MSFT"],
                "startDate": "2025-01-01",
                "endDate": "2025-01-03",
                "rowLimit": 10,
            },
            invocation(ohlcv),
        )
        assert isinstance(candles["series"][0]["rows"][0]["volume"], str)
        provider.fail = True
        failed = app.state.execute(tool, {"symbols": ["MSFT"]}, invocation(tool))
        assert failed["quotes"] == []
        assert "credential-sensitive" not in json.dumps(failed)
    app.state.engine.dispose()


def test_notes_transaction_dedupe_conflict_and_unknown_while_in_progress(database_url):
    from notes_plugin.main import Note

    app = notes_app(database_url)
    tool = "example/notes/create"
    context = invocation(tool)
    operation_id = context["operationId"]
    with TestClient(app):
        entered, proceed = threading.Event(), threading.Event()

        def effect(session):
            session.add(
                Note(id=operation_id, collection="research", title="Durable", text="Original")
            )
            session.flush()
            entered.set()
            assert proceed.wait(5)
            return {
                "id": operation_id,
                "collection": "research",
                "title": "Durable",
                "text": "Original",
            }

        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(
                app.state.journal.write,
                operation_id,
                tool,
                {"title": "Durable", "text": "Original"},
                effect,
                scope=context["resourceBindings"],
            )
            assert entered.wait(5)
            assert app.state.journal.query(operation_id)["status"] == "unknown"
            proceed.set()
            result = future.result(timeout=5)
        assert app.state.journal.query(operation_id) == {"status": "succeeded", "output": result}
        assert app.state.execute(tool, {"title": "Durable", "text": "Original"}, context) == result
        with pytest.raises(ValueError, match="operation_input_conflict"):
            app.state.execute(tool, {"title": "Changed", "text": "Original"}, context)
        assert (
            len(
                app.state.execute("example/notes/search", {}, invocation("example/notes/search"))[
                    "notes"
                ]
            )
            == 1
        )

        def abort(session):
            session.add(
                Note(id="rollback", collection="research", title="rollback", text="rollback")
            )
            session.flush()
            raise RuntimeError("rollback")

        with pytest.raises(RuntimeError):
            app.state.journal.write("rollback", tool, {}, abort)
        assert app.state.journal.query("rollback")["status"] == "not_found"
    app.state.engine.dispose()


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _launch(root, database_url, port):
    endpoint = f"http://127.0.0.1:{port}/mcp/"
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(root / "runtime"), str(root / "notes")]),
        "PLUGIN_DATABASE_URL": database_url,
        "PLUGIN_ENDPOINT": endpoint,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "notes_plugin.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError("Plugin exited before becoming ready")
            try:
                release = httpx.get(f"http://127.0.0.1:{port}/release", timeout=0.2).json()
                return process, endpoint, release
            except httpx.HTTPError:
                time.sleep(0.05)
        raise AssertionError("Plugin did not become ready")
    except BaseException:
        process.terminate()
        process.wait(timeout=10)
        raise


def test_real_mcp_third_plugin_upgrade_keeps_old_release_and_dedupes(database_url, tmp_path):
    shutil.copytree(
        PLUGINS / "runtime", tmp_path / "runtime", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copytree(
        PLUGINS / "notes", tmp_path / "notes", ignore=shutil.ignore_patterns("__pycache__", ".venv")
    )
    (tmp_path / "notes" / "VERSION").write_text("1.3.0\n")
    upgraded_source = tmp_path / "notes" / "notes_plugin" / "main.py"
    original = upgraded_source.read_text()
    changed = original.replace('"text": arguments["text"],', '"text": arguments["text"].upper(),')
    assert changed != original
    upgraded_source.write_text(changed)
    old, old_url, old_release = _launch(PLUGINS, database_url, _free_port())
    new, new_url, new_release = _launch(tmp_path, database_url, _free_port())

    async def scenario():
        assert old_release["artifactDigest"] != new_release["artifactDigest"]
        assert old_release["releaseId"] == "1.2.0" and new_release["releaseId"] == "1.3.0"
        context = invocation("example/notes/create")
        async with streamable_http_client(old_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.protocolVersion == "2025-11-25"
                listed = await session.list_tools()
                identity = listed.meta["signaldeck/release"]
                metadata = {"signaldeck/release": identity, "signaldeck/context": context}
                first = await session.call_tool(
                    "example/notes/create",
                    {"title": "Agent notes", "text": "confirmed"},
                    meta=metadata,
                )
                assert not first.isError
                # Ignore the response as if its network delivery had been lost, then query.
                query = await session.call_tool(
                    "signaldeck/operations/query",
                    {"operationId": context["operationId"]},
                    meta=metadata,
                )
                assert query.structuredContent["status"] == "succeeded"
                again = await session.call_tool(
                    "example/notes/create",
                    {"title": "Agent notes", "text": "confirmed"},
                    meta=metadata,
                )
                assert again.structuredContent == first.structuredContent
                denied = {**metadata, "signaldeck/context": {**context, "toolGrants": []}}
                assert (
                    await session.call_tool(
                        "example/notes/create", {"title": "denied", "text": "x"}, meta=denied
                    )
                ).isError
                invalid = await session.call_tool(
                    "example/notes/create",
                    {"title": "bad", "text": "x", "secret": "must-not-leak"},
                    meta=metadata,
                )
                assert invalid.isError and "must-not-leak" not in invalid.model_dump_json()
                async with streamable_http_client(new_url) as (read2, write2, _):
                    async with ClientSession(read2, write2) as new_session:
                        await new_session.initialize()
                        rejected = await new_session.call_tool(
                            "example/notes/create",
                            {"title": "Agent notes", "text": "confirmed"},
                            meta=metadata,
                        )
                        assert rejected.isError
                        new_identity = (await new_session.list_tools()).meta["signaldeck/release"]
                        upgraded = await new_session.call_tool(
                            "example/notes/create",
                            {"title": "Upgraded", "text": "new behavior"},
                            meta={
                                "signaldeck/release": new_identity,
                                "signaldeck/context": invocation("example/notes/create"),
                            },
                        )
                        assert not upgraded.isError
                        assert upgraded.structuredContent["text"] == "NEW BEHAVIOR"
                assert (
                    await session.call_tool(
                        "example/notes/create",
                        {"title": "Agent notes", "text": "confirmed"},
                        meta=metadata,
                    )
                ).structuredContent == first.structuredContent

        from app.domain.tool_contracts import PluginRelease, ToolInvocationContext
        from app.infrastructure.mcp_transport import McpToolTransport

        class Headers:
            async def resolve(self, plugin_id, resources):
                return {}

        release = PluginRelease.model_validate(old_release)
        definition = next(t for t in release.tools if t.tool_id == "example/notes/create")
        scoped = invocation(definition.tool_id)
        scoped["resourceBindings"] = {
            "notes-workspace": {"pluginId": "example/notes", "scope": {"collection": "gateway"}}
        }
        transport = McpToolTransport(Headers())
        context = ToolInvocationContext.model_validate(scoped)
        result = await transport.execute(
            release, definition, {"title": "Gateway", "text": "Scoped"}, context
        )
        assert result.status == "succeeded", result
        assert result.output["collection"] == "gateway"
        queried = await transport.query(release, definition, context)
        assert queried.output == result.output

    try:
        asyncio.run(scenario())
    finally:
        for process in [old, new]:
            process.terminate()
            process.wait(timeout=10)


def test_plugin_database_role_cannot_read_core_private_tables(database_url):
    admin = create_engine(database_url)
    role = "plugin_" + uuid4().hex
    # This database and role belong solely to this test and are removed below.
    with admin.begin() as connection:
        connection.execute(text("CREATE TABLE core_private (value text)"))
        connection.execute(text(f"CREATE ROLE \"{role}\" LOGIN PASSWORD 'isolated-test-password'"))
        connection.execute(text(f'GRANT USAGE, CREATE ON SCHEMA public TO "{role}"'))
    plugin_url = (
        make_url(database_url)
        .set(username=role, password="isolated-test-password")
        .render_as_string(hide_password=False)
    )
    app = notes_app(plugin_url)
    try:
        with TestClient(app):
            tool = "example/notes/create"
            assert (
                app.state.execute(
                    tool, {"title": "Isolated", "text": "Own database access"}, invocation(tool)
                )["title"]
                == "Isolated"
            )
            with app.state.engine.connect() as connection:
                with pytest.raises(Exception, match="permission denied"):
                    connection.execute(text("SELECT * FROM core_private"))
        assert "isolated-test-password" not in json.dumps(descriptor(app))
    finally:
        app.state.engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{role}" CASCADE'))
            connection.execute(text(f'DROP ROLE "{role}"'))
        admin.dispose()


def test_resource_scopes_are_enforced_in_plugin_business_queries(database_url):
    app = notes_app(database_url)
    with TestClient(app):
        create = "example/notes/create"
        context = invocation(create)
        app.state.execute(create, {"title": "First collection", "text": "research"}, context)
        other = invocation(create)
        other["resourceBindings"]["notes-workspace"]["collection"] = "private"
        app.state.execute(create, {"title": "Second collection", "text": "private"}, other)
        result = app.state.execute("example/notes/search", {}, invocation("example/notes/search"))
        assert [note["title"] for note in result["notes"]] == ["First collection"]
        changed = {**context, "resourceBindings": other["resourceBindings"]}
        with pytest.raises(ValueError, match="operation_input_conflict"):
            app.state.execute(create, {"title": "First collection", "text": "research"}, changed)
        with pytest.raises(ValueError, match="operation_scope_conflict"):
            app.state.journal.query(context["operationId"], other["resourceBindings"], [create])
    app.state.engine.dispose()
    finance = finance_app(database_url, DeterministicQuoteProvider())
    with TestClient(finance):
        quote = "signaldeck/finance/market_data_quote_lookup"
        with pytest.raises(ValueError, match="finance_symbol_not_granted"):
            finance.state.execute(quote, {"symbols": ["AAPL"]}, invocation(quote))
    finance.state.engine.dispose()


def test_oracle_extracted_provider_result_validates_advertised_contract(monkeypatch):
    from jsonschema import Draft202012Validator
    from oracle_plugin import runtime_market_sentiment

    monkeypatch.setattr(
        runtime_market_sentiment._HttpxFearGreedJsonClient,
        "get_json",
        lambda *args, **kwargs: {
            "fear_and_greed": {"score": 42, "rating": "fear", "timestamp": 1704067200000}
        },
    )
    name = "signaldeck/digital-oracle/market_sentiment_lookup"
    output = oracle_app.state.execute(name, {"indicator": "fear_greed"}, invocation(name))
    contract = next(tool for tool in descriptor(oracle_app)["tools"] if tool["toolId"] == name)
    Draft202012Validator(contract["outputSchema"]).validate(output)
    assert output["toolKey"] == name
    assert output["warnings"]
    assert all(isinstance(warning["details"], list) for warning in output["warnings"])


def test_plugin_release_never_projects_credentials_from_urls(monkeypatch):
    monkeypatch.setenv("PLUGIN_ENDPOINT", "http://user:must-not-leak@localhost:8000/mcp/")
    with pytest.raises(ValueError) as error:
        notes_app("postgresql+psycopg://localhost/unused")
    assert "must-not-leak" not in str(error.value)


def test_notes_1_1_schema_remains_live_beside_1_2(database_url, tmp_path):
    # Executable 1.1 source captured from a518c65e, before provenance existed.
    shutil.copytree(
        PLUGINS / "runtime", tmp_path / "runtime", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copytree(
        PLUGINS / "notes", tmp_path / "notes", ignore=shutil.ignore_patterns("__pycache__", ".venv")
    )
    legacy = Path(__file__).parent / "fixtures" / "notes_1_1"
    for name in ("main.py", "web.py"):
        shutil.copyfile(legacy / f"{name}.txt", tmp_path / "notes" / "notes_plugin" / name)
    (tmp_path / "notes" / "VERSION").write_text("1.1.0\n")
    old, old_url, old_release = _launch(tmp_path, database_url, _free_port())
    new = None

    async def call(url, release, operation, arguments):
        async with streamable_http_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(
                    "example/notes/create",
                    arguments,
                    meta={
                        "signaldeck/release": {
                            key: release[key]
                            for key in ("pluginId", "releaseId", "artifactDigest", "contractDigest")
                        },
                        "signaldeck/context": invocation("example/notes/create", operation),
                    },
                )

    try:
        arguments = {"title": "Summary", "text": "Original historical bytes"}
        saved = asyncio.run(call(old_url, old_release, "legacy-frozen", arguments))
        assert not saved.isError
        assert set(saved.structuredContent) == {"id", "collection", "title", "text"}
        new, new_url, new_release = _launch(PLUGINS, database_url, _free_port())
        assert new_release["releaseId"] == "1.2.0"
        assert new_release["contractDigest"] != old_release["contractDigest"]
        assert asyncio.run(call(new_url, old_release, "legacy-frozen", arguments)).isError
        repeated = asyncio.run(call(old_url, old_release, "legacy-frozen", arguments))
        assert repeated.structuredContent == saved.structuredContent
        fresh = asyncio.run(
            call(new_url, new_release, "new-release", {**arguments, "sourceKind": "original"})
        )
        assert not fresh.isError and fresh.structuredContent["sourceKind"] == "original"
        with httpx.Client() as client:
            response = client.get(
                new_url.replace("/mcp/", "/api/note"), params={"id": "legacy-frozen"}
            )
            assert response.json() == {
                **saved.structuredContent,
                "sourceKind": "unclassified",
                "sourceNoteIds": [],
            }
        # New startup has not changed what the original process returns.
        assert (
            asyncio.run(call(old_url, old_release, "legacy-frozen", arguments)).structuredContent
            == saved.structuredContent
        )
    finally:
        for process in (old, new):
            if process is not None:
                process.terminate()
                process.wait(timeout=10)

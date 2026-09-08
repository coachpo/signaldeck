"""Real HTTP sessions release closed state and keep active calls associated."""

import asyncio
import sys
from pathlib import Path

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.server.lowlevel import Server

from tests.test_durable_runtime_support import serve_app

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins/runtime"))
from plugin_runtime.sessions import PluginSessions  # noqa: E402


def test_closed_sessions_are_forgotten_and_expired_identity_returns_404():
    async def scenario():
        manager = PluginSessions(Server("session-cleanup"))
        async with manager.run(), serve_app(manager.handle_request) as endpoint:
            for _ in range(3):
                async with streamable_http_client(endpoint) as (read, write, get_id):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        identity = get_id()
                        assert identity in manager._server_instances
                assert manager._server_instances == {}
                assert manager.last_activity == {} and manager.active_posts == {}
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        endpoint,
                        headers={
                            "MCP-Session-Id": identity,
                            "Accept": "text/event-stream",
                        },
                    )
                    assert response.status_code == 404

    asyncio.run(scenario())


def test_idle_expiry_keeps_active_post_and_expires_abandoned_session():
    async def scenario():
        server = Server("session-expiry")
        entered, release = asyncio.Event(), asyncio.Event()

        @server.list_tools()
        async def list_tools():
            return [types.Tool(name="held", inputSchema={"type": "object"})]

        @server.call_tool()
        async def held(name, arguments):
            entered.set()
            await release.wait()
            return {"finished": True}

        manager = PluginSessions(server, idle_seconds=0.05)
        async with manager.run(), serve_app(manager.handle_request) as endpoint:
            async with streamable_http_client(endpoint) as (read, write, get_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    identity = get_id()
                    operation = asyncio.create_task(session.call_tool("held", {}))
                    try:
                        await asyncio.wait_for(entered.wait(), timeout=3)
                        await asyncio.sleep(0.06)
                        await manager.expire_idle()
                        assert identity in manager._server_instances
                        assert not operation.done()
                        release.set()
                        await asyncio.wait_for(operation, timeout=3)
                        await asyncio.sleep(0.06)
                        await manager.expire_idle()
                        assert identity not in manager._server_instances
                        assert identity not in manager.last_activity
                    finally:
                        release.set()
                        await asyncio.gather(operation, return_exceptions=True)

    asyncio.run(scenario())

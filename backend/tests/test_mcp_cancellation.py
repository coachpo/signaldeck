"""Cancellation cleanup cannot prolong execution or disclose request data."""

import asyncio
import json

import httpx
import pytest

from app.infrastructure.mcp_cancellation import ToolRequestCancellation


@pytest.mark.parametrize("outcome", ["unavailable", "held"])
def test_notification_failure_is_bounded_and_preserves_cancellation(outcome, caplog):
    async def scenario():
        cancellation = ToolRequestCancellation()
        observed = []
        cleanup_stopped = asyncio.Event()
        credential = "sentinel-cancellation-credential"

        async def transport(request):
            observed.append(json.loads(request.content))
            assert request.headers["MCP-Session-Id"] == "wire-session"
            assert request.headers["MCP-Protocol-Version"] == "2025-11-25"
            assert request.headers["Authorization"] == f"Bearer {credential}"
            try:
                if outcome == "held":
                    await asyncio.Event().wait()
                raise httpx.ReadError(credential)
            finally:
                cleanup_stopped.set()

        class InterruptedSession:
            async def call_tool(self, name, arguments, *, meta):
                await cancellation.observe_request(
                    httpx.Request(
                        "POST",
                        "http://plugin.test/mcp/",
                        json={"jsonrpc": "2.0", "method": "tools/call", "id": 17},
                    )
                )
                raise asyncio.CancelledError

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(transport),
            headers={"Authorization": f"Bearer {credential}"},
        ) as client:
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(
                    cancellation.call_tool(
                        InterruptedSession(),
                        client,
                        "http://plugin.test/mcp/",
                        "2025-11-25",
                        lambda: "wire-session",
                        "example/plugin/write",
                        {"text": "private-business-input"},
                        {"scope": "private-scope"},
                    ),
                    timeout=3,
                )
        assert cancellation.cancelled and cleanup_stopped.is_set()
        assert observed == [
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {
                    "requestId": 17,
                    "reason": "Execution stopped waiting for this request",
                },
            }
        ]
        assert credential not in caplog.text
        assert "private-business-input" not in caplog.text

    asyncio.run(scenario())


def test_cancellation_before_tool_dispatch_never_cancels_initialize():
    async def scenario():
        cancellation = ToolRequestCancellation()
        await cancellation.observe_request(
            httpx.Request(
                "POST",
                "http://plugin.test/mcp/",
                json={"jsonrpc": "2.0", "method": "initialize", "id": 0},
            )
        )

        class NotIssued:
            async def call_tool(self, *args, **kwargs):
                raise asyncio.CancelledError

        def unexpected(request):
            pytest.fail("No cancellable tool request has been issued")

        async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
            with pytest.raises(asyncio.CancelledError):
                await cancellation.call_tool(
                    NotIssued(),
                    client,
                    "http://plugin.test/mcp/",
                    "2025-11-25",
                    lambda: None,
                    "example/plugin/write",
                    {},
                    {},
                )
        assert cancellation.request_id is None

    asyncio.run(scenario())


def test_repeated_task_cancellation_finishes_one_notification_before_transport_closes():
    async def scenario():
        cancellation = ToolRequestCancellation()
        tool_started, notification_started, release = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )
        delivered = []

        class HeldSession:
            async def call_tool(self, name, arguments, *, meta):
                await cancellation.observe_request(
                    httpx.Request(
                        "POST",
                        "http://plugin.test/mcp/",
                        json={"jsonrpc": "2.0", "method": "tools/call", "id": 23},
                    )
                )
                tool_started.set()
                await asyncio.Event().wait()

        async def transport(request):
            notification_started.set()
            await release.wait()
            delivered.append(json.loads(request.content))
            return httpx.Response(202)

        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            request = asyncio.create_task(
                cancellation.call_tool(
                    HeldSession(),
                    client,
                    "http://plugin.test/mcp/",
                    "2025-11-25",
                    lambda: None,
                    "example/plugin/write",
                    {},
                    {},
                )
            )
            try:
                await asyncio.wait_for(tool_started.wait(), timeout=3)
                request.cancel("initial-stop")
                await asyncio.wait_for(notification_started.wait(), timeout=3)
                request.cancel("repeated-stop")
                release.set()
                with pytest.raises(asyncio.CancelledError) as stopped:
                    await asyncio.wait_for(request, timeout=3)
                assert delivered == [
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/cancelled",
                        "params": {
                            "requestId": 23,
                            "reason": "Execution stopped waiting for this request",
                        },
                    }
                ]
                assert str(stopped.value) == "initial-stop"
                assert not client.is_closed
            finally:
                release.set()
                if not request.done():
                    request.cancel()
                await asyncio.gather(request, return_exceptions=True)

    asyncio.run(scenario())

"""Bounded MCP cancellation using the public HTTP and session contracts."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import anyio
import httpx
from mcp import ClientSession, types


class ToolRequestCancellation:
    def __init__(self) -> None:
        self.request_id: str | int | None = None
        self.cancelled = False

    async def observe_request(self, request: httpx.Request) -> None:
        if request.method != "POST":
            return
        message = json.loads(request.content)
        if message.get("method") == "tools/call":
            self.request_id = message["id"]

    async def call_tool(
        self,
        session: ClientSession,
        client: httpx.AsyncClient,
        endpoint: str,
        protocol: str,
        session_id: Callable[[], str | None],
        name: str,
        arguments: dict[str, Any],
        metadata: dict[str, Any],
    ) -> types.CallToolResult:
        self.request_id = None
        try:
            return await session.call_tool(name, arguments, meta=metadata)
        except asyncio.CancelledError:
            self.cancelled = True
            await self._notify(client, endpoint, protocol, session_id())
            raise

    async def _notify(
        self, client: httpx.AsyncClient, endpoint: str, protocol: str, session_id: str | None
    ) -> None:
        if self.request_id is None:
            return
        notification = types.CancelledNotification(
            params=types.CancelledNotificationParams(
                requestId=self.request_id, reason="Execution stopped waiting for this request"
            )
        )
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": protocol,
        }
        if session_id is not None:
            headers["MCP-Session-Id"] = session_id

        async def send() -> None:
            try:
                async with asyncio.timeout(1):
                    await client.post(
                        endpoint,
                        headers=headers,
                        json={
                            "jsonrpc": "2.0",
                            **notification.model_dump(by_alias=True, exclude_none=True),
                        },
                        timeout=1,
                    )
            except Exception:
                # A lost cancellation remains uncertainty, not permission to replay a write.
                pass

        # The SDK notification helper only enqueues. Keep this HTTP send alive until
        # its own deadline, even if parent asyncio or AnyIO cancellation repeats.
        # call_tool re-raises the original cancellation after the transport can close.
        with anyio.CancelScope(shield=True):
            pending = asyncio.create_task(send())
            while not pending.done():
                try:
                    await asyncio.shield(pending)
                except asyncio.CancelledError:
                    pass

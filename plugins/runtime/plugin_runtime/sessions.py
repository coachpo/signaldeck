"""Bound the lifetime of MCP wire sessions independently of business operations."""

import time
from contextlib import asynccontextmanager

import anyio
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager


class PluginSessions(StreamableHTTPSessionManager):
    def __init__(self, server, *, idle_seconds=60):
        super().__init__(app=server, json_response=True, stateless=False)
        self.idle_seconds = idle_seconds
        self.last_activity = {}
        self.active_posts = {}

    @asynccontextmanager
    async def run(self):
        async with super().run(), anyio.create_task_group() as tasks:
            tasks.start_soon(self._expiry_loop)
            try:
                yield
            finally:
                tasks.cancel_scope.cancel()

    async def _expiry_loop(self):
        while True:
            await anyio.sleep(1)
            await self.expire_idle()

    async def expire_idle(self):
        now = time.monotonic()
        # MCP 1.26.0 has no expiry API and retains terminated transports in this
        # registry. Keep its one private access here; expired identities still get 404.
        for identity, transport in list(self._server_instances.items()):
            expired = (
                not self.active_posts.get(identity)
                and now - self.last_activity.get(identity, now) >= self.idle_seconds
            )
            if transport.is_terminated or expired:
                await transport.terminate()
                self._forget(identity)

    def _forget(self, identity):
        self._server_instances.pop(identity, None)
        self.last_activity.pop(identity, None)
        self.active_posts.pop(identity, None)

    async def handle_request(self, scope, receive, send):
        header = dict(scope.get("headers", [])).get(b"mcp-session-id")
        identity = header.decode() if header else None
        active = identity is not None and scope.get("method") == "POST"
        if identity in self._server_instances:
            self.last_activity[identity] = time.monotonic()
            if active:
                self.active_posts[identity] = self.active_posts.get(identity, 0) + 1

        async def observed_send(message):
            if message["type"] == "http.response.start":
                assigned = dict(message.get("headers", [])).get(b"mcp-session-id")
                if assigned and assigned.decode() in self._server_instances:
                    self.last_activity[assigned.decode()] = time.monotonic()
            await send(message)

        try:
            await super().handle_request(scope, receive, observed_send)
        finally:
            transport = self._server_instances.get(identity)
            if transport is not None:
                if active:
                    self.active_posts[identity] -= 1
                if transport.is_terminated:
                    self._forget(identity)
                else:
                    self.last_activity[identity] = time.monotonic()

"""Forward one cancellation to a Temporal operation and await its actual termination."""

from __future__ import annotations

import asyncio


async def await_cancel_once[T](handle: asyncio.Future[T], *, cancel_handle: bool = True) -> T:
    try:
        return await asyncio.shield(handle)
    except asyncio.CancelledError:
        if cancel_handle and not handle.done():
            handle.cancel()
        while True:
            try:
                await asyncio.shield(handle)
            except asyncio.CancelledError:
                if not handle.done():
                    continue
            except Exception:
                # The operation's cancellation/failure is consumed before the caller's
                # original cancellation propagates. SDK eviction BaseExceptions escape.
                pass
            break
        raise

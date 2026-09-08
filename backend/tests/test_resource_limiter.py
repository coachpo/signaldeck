from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.infrastructure.resource_limiter import (
    PostgresResourceLimiter,
    ResourceLimit,
    ResourcePermitRow,
    ResourceRateRow,
)


@pytest.fixture
def limiter_factory(database_url):
    engine = create_engine(database_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    PostgresResourceLimiter(factory).initialize()
    yield factory
    engine.dispose()


def resources(concurrency=1, rps=10000):
    return {"service-a": {"maxConcurrentCalls": concurrency, "requestsPerSecond": rps}}


def deadline(seconds=3):
    return datetime.now(UTC) + timedelta(seconds=seconds)


def test_two_workers_share_concurrency_and_cancelled_waiter_cannot_orphan_permit(limiter_factory):
    async def scenario():
        blocked = asyncio.Event()
        entered = asyncio.Event()
        release = asyncio.Event()
        loop = asyncio.get_running_loop()

        class ObservedLimiter(PostgresResourceLimiter):
            def _try_acquire(self, *args):
                acquired = super()._try_acquire(*args)
                if not acquired:
                    loop.call_soon_threadsafe(blocked.set)
                return acquired

        first = PostgresResourceLimiter(limiter_factory)
        second = ObservedLimiter(limiter_factory)

        async def hold():
            async with first.acquire(resources(), "run-one:operation", deadline()):
                entered.set()
                await release.wait()

        async def wait():
            async with second.acquire(resources(), "run-two:operation", deadline()):
                pytest.fail("Second worker exceeded external concurrency")

        holder = asyncio.create_task(hold())
        await asyncio.wait_for(entered.wait(), 1)
        waiting = asyncio.create_task(wait())
        await asyncio.wait_for(blocked.wait(), 1)
        with limiter_factory() as session:
            assert session.scalar(select(func.count()).select_from(ResourcePermitRow)) == 1
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        release.set()
        await holder
        async with second.acquire(resources(), "run-three:operation", deadline()):
            with limiter_factory() as session:
                assert session.scalar(select(func.count()).select_from(ResourcePermitRow)) == 1
        with limiter_factory() as session:
            assert session.scalar(select(func.count()).select_from(ResourcePermitRow)) == 0

    asyncio.run(scenario())


def test_total_deadline_and_cancellation_release_active_permit(limiter_factory):
    async def scenario():
        limiter = PostgresResourceLimiter(limiter_factory)
        entered = asyncio.Event()

        async def hold():
            async with limiter.acquire(resources(), "holder", deadline()):
                entered.set()
                await asyncio.Event().wait()

        holder = asyncio.create_task(hold())
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(TimeoutError):
            async with limiter.acquire(resources(), "deadline", deadline(0.12)):
                pytest.fail("Deadline waiter unexpectedly entered")
        holder.cancel()
        with pytest.raises(asyncio.CancelledError):
            await holder
        with limiter_factory() as session:
            assert session.scalar(select(func.count()).select_from(ResourcePermitRow)) == 0
        async with limiter.acquire(resources(), "next", deadline()):
            pass

    asyncio.run(scenario())


def test_crashed_worker_lease_expires_and_heartbeat_keeps_live_worker(limiter_factory):
    async def scenario():
        limiter = PostgresResourceLimiter(limiter_factory, lease_seconds=0.15, poll_seconds=0.01)
        # Simulate a process stopping after its committed permit without a heartbeat.
        assert limiter._try_acquire(
            {"service-a": ResourceLimit(1, 0.0001)}, str(uuid4()), "crashed", deadline()
        )
        started = time.monotonic()
        async with limiter.acquire(resources(), "recovered", deadline()):
            assert time.monotonic() - started >= 0.12
            with limiter_factory() as session:
                owners = list(session.scalars(select(ResourcePermitRow.operation_id)))
                assert owners == ["recovered"]

    asyncio.run(scenario())


def test_rps_spacing_is_shared_between_workers_after_permit_release(limiter_factory):
    async def scenario():
        first, second = PostgresResourceLimiter(limiter_factory), PostgresResourceLimiter(
            limiter_factory
        )
        async with first.acquire(resources(concurrency=4, rps=4), "one", deadline()):
            with limiter_factory() as session:
                first_next = session.get(ResourceRateRow, "service-a").next_start_at
        async with second.acquire(resources(concurrency=4, rps=4), "two", deadline()):
            with limiter_factory() as session:
                second_next = session.get(ResourceRateRow, "service-a").next_start_at
        assert (second_next - first_next).total_seconds() >= 0.25

    asyncio.run(scenario())


def test_multiple_resources_are_acquired_atomically(limiter_factory):
    async def scenario():
        first, second = PostgresResourceLimiter(limiter_factory), PostgresResourceLimiter(
            limiter_factory
        )
        async with first.acquire(resources(), "one", deadline()):
            with pytest.raises(TimeoutError):
                async with second.acquire({**resources(), "service-b": {}}, "two", deadline(0.1)):
                    pytest.fail("Unavailable composite resources unexpectedly entered")
            with limiter_factory() as session:
                assert list(session.scalars(select(ResourcePermitRow.resource_id))) == ["service-a"]
                assert session.get(ResourceRateRow, "service-b") is None

    asyncio.run(scenario())


def test_heartbeat_preserves_permit_beyond_initial_crash_lease(limiter_factory):
    async def scenario():
        renewed = asyncio.Event()
        entered = asyncio.Event()
        release = asyncio.Event()
        loop = asyncio.get_running_loop()

        class HeartbeatObservedLimiter(PostgresResourceLimiter):
            renewals = 0

            def _renew(self, *args):
                super()._renew(*args)
                self.renewals += 1
                if self.renewals >= 4:
                    loop.call_soon_threadsafe(renewed.set)

        first = HeartbeatObservedLimiter(limiter_factory, lease_seconds=0.3)
        second = PostgresResourceLimiter(limiter_factory, lease_seconds=0.3)

        async def hold():
            async with first.acquire(resources(), "still-alive", deadline()):
                entered.set()
                await release.wait()

        task = asyncio.create_task(hold())
        await asyncio.wait_for(entered.wait(), 1)
        with limiter_factory() as session:
            original_expiry = session.scalar(select(ResourcePermitRow.expires_at))
        await asyncio.wait_for(renewed.wait(), 2)
        assert not second._try_acquire(
            {"service-a": ResourceLimit(1, 0.0001)}, str(uuid4()), "other", deadline()
        )
        with limiter_factory() as session:
            assert session.scalar(select(ResourcePermitRow.expires_at)) > original_expiry
        release.set()
        await task

    asyncio.run(scenario())

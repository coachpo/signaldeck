"""PostgreSQL permits for cross-worker external I/O concurrency and request spacing."""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Float, Integer, String, delete, select, text, update
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class ResourceLimitBase(DeclarativeBase):
    pass


class ResourcePermitRow(ResourceLimitBase):
    __tablename__ = "platform_io_resource_permits"
    reservation_id: Mapped[str] = mapped_column(String, primary_key=True)
    resource_id: Mapped[str] = mapped_column(String, primary_key=True)
    operation_id: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    concurrency_limit: Mapped[int] = mapped_column(Integer)
    spacing_seconds: Mapped[float] = mapped_column(Float)


class ResourceRateRow(ResourceLimitBase):
    __tablename__ = "platform_io_resource_rates"
    resource_id: Mapped[str] = mapped_column(String, primary_key=True)
    next_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResourceLeaseLost(RuntimeError):
    pass


@dataclass(frozen=True)
class ResourceLimit:
    concurrency: int
    spacing_seconds: float


def _limits(resources: dict[str, dict[str, Any]]) -> dict[str, ResourceLimit]:
    result = {}
    for resource_id, config in sorted(resources.items()):
        concurrency = config.get("maxConcurrentCalls", 4)
        rate = config.get("requestsPerSecond", 10)
        if (
            not resource_id
            or len(resource_id) > 512
            or isinstance(concurrency, bool)
            or not isinstance(concurrency, int)
            or not 1 <= concurrency <= 1000
            or isinstance(rate, bool)
            or not isinstance(rate, (float, int))
            or not math.isfinite(rate)
            or not 0 < rate <= 10000
        ):
            raise ValueError("Invalid frozen resource limits")
        result[resource_id] = ResourceLimit(concurrency, 1 / rate)
    return result


class PostgresResourceLimiter:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        lease_seconds: float = 30,
        poll_seconds: float = 0.05,
    ):
        if lease_seconds <= 0 or poll_seconds <= 0:
            raise ValueError("Resource lease and polling durations must be positive")
        self.session_factory = session_factory
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds

    def initialize(self) -> None:
        """Create only the limiter-owned tables during process composition."""
        with self.session_factory() as session, session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": "io-resource-schema"},
            )
            ResourceLimitBase.metadata.create_all(session.connection())

    @asynccontextmanager
    async def acquire(
        self, resources: dict[str, dict[str, Any]], operation_id: str, deadline: datetime
    ) -> AsyncIterator[None]:
        if deadline.tzinfo is None:
            raise ValueError("Resource deadline must include a timezone")
        limits = _limits(resources)
        reservation_id = str(uuid4())
        try:
            while True:
                remaining = (deadline - datetime.now(UTC)).total_seconds()
                if remaining <= 0:
                    raise TimeoutError("External resource deadline exceeded")
                reserve = asyncio.create_task(
                    asyncio.to_thread(
                        self._try_acquire, limits, reservation_id, operation_id, deadline
                    )
                )
                try:
                    acquired = await asyncio.shield(reserve)
                except asyncio.CancelledError:
                    # Cancellation cannot orphan a transaction that is still committing.
                    await reserve
                    raise
                if acquired:
                    break
                await asyncio.sleep(min(self.poll_seconds, remaining))
            async with asyncio.timeout(max(0, (deadline - datetime.now(UTC)).total_seconds())):
                async with asyncio.TaskGroup() as tasks:
                    heartbeat = tasks.create_task(self._heartbeat(reservation_id, limits, deadline))
                    try:
                        yield
                    finally:
                        heartbeat.cancel()
        finally:
            await asyncio.shield(asyncio.to_thread(self._release, reservation_id))

    def _try_acquire(
        self,
        limits: dict[str, ResourceLimit],
        reservation_id: str,
        operation_id: str,
        deadline: datetime,
    ) -> bool:
        with self.session_factory() as session, session.begin():
            for resource_id in limits:
                locked = session.scalar(
                    text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": "io-resource:" + resource_id},
                )
                if not locked:
                    return False
            now = session.scalar(select(text("clock_timestamp()")))
            assert isinstance(now, datetime)
            if now >= deadline:
                raise TimeoutError("External resource deadline exceeded")
            session.execute(delete(ResourcePermitRow).where(ResourcePermitRow.expires_at <= now))
            rates = {}
            effective_spacing = {}
            for resource_id, limit in limits.items():
                active = list(
                    session.scalars(
                        select(ResourcePermitRow).where(
                            ResourcePermitRow.resource_id == resource_id
                        )
                    )
                )
                concurrency = min([limit.concurrency] + [row.concurrency_limit for row in active])
                if len(active) >= concurrency:
                    return False
                rate = session.get(ResourceRateRow, resource_id)
                if rate is not None and rate.next_start_at > now:
                    return False
                rates[resource_id] = rate
                effective_spacing[resource_id] = max(
                    [limit.spacing_seconds] + [row.spacing_seconds for row in active]
                )
            for resource_id, limit in limits.items():
                spacing = effective_spacing[resource_id]
                session.add(
                    ResourcePermitRow(
                        reservation_id=reservation_id,
                        resource_id=resource_id,
                        operation_id=operation_id,
                        concurrency_limit=limit.concurrency,
                        spacing_seconds=limit.spacing_seconds,
                        expires_at=min(deadline, now + timedelta(seconds=self.lease_seconds)),
                    )
                )
                next_start = now + timedelta(seconds=spacing)
                rate = rates[resource_id]
                if rate is None:
                    session.add(ResourceRateRow(resource_id=resource_id, next_start_at=next_start))
                else:
                    rate.next_start_at = next_start
            return True

    async def _heartbeat(
        self, reservation_id: str, limits: dict[str, ResourceLimit], deadline: datetime
    ) -> None:
        while True:
            await asyncio.sleep(self.lease_seconds / 3)
            await asyncio.to_thread(self._renew, reservation_id, len(limits), deadline)

    def _renew(self, reservation_id: str, expected: int, deadline: datetime) -> None:
        with self.session_factory() as session, session.begin():
            now = session.scalar(select(text("clock_timestamp()")))
            assert isinstance(now, datetime)
            rows = session.scalars(
                update(ResourcePermitRow)
                .where(
                    ResourcePermitRow.reservation_id == reservation_id,
                    ResourcePermitRow.expires_at > now,
                )
                .values(expires_at=min(deadline, now + timedelta(seconds=self.lease_seconds)))
                .returning(ResourcePermitRow.resource_id)
            )
            if len(list(rows)) != expected:
                raise ResourceLeaseLost("External resource permit expired")

    def _release(self, reservation_id: str) -> None:
        with self.session_factory() as session, session.begin():
            session.execute(
                delete(ResourcePermitRow).where(ResourcePermitRow.reservation_id == reservation_id)
            )

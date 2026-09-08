"""PostgreSQL desired schedule configuration and idempotent trigger receipts."""

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.domain.execution import ApplicationError
from app.domain.schedules import (
    ScheduleDefinition,
    ScheduleFireRecord,
    ScheduleRecord,
    ScheduleTriggerReceipt,
)
from app.infrastructure.platform_models import PlatformBase
from app.infrastructure.platform_transactions import lock_identity
from app.infrastructure.schedule_fires import ScheduleFireRow, ScheduleFireStore


class ScheduleRow(PlatformBase):
    __tablename__ = "platform_schedules"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(Integer)
    synced_revision: Mapped[int] = mapped_column(Integer, default=0)
    desired_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_error_code: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScheduleTriggerRow(PlatformBase):
    __tablename__ = "platform_schedule_triggers"
    __table_args__ = (UniqueConstraint("schedule_id", "identity_time"),)
    schedule_id: Mapped[str] = mapped_column(ForeignKey(ScheduleRow.id), primary_key=True)
    trigger_id: Mapped[str] = mapped_column(String, primary_key=True)
    identity_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String)


def _lock(session: Session, schedule_id: str) -> None:
    # Never block an event loop waiting for a transaction which is awaiting network I/O.
    acquired = session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtextextended(:identity, 0))"),
        {"identity": "schedule:" + schedule_id},
    )
    if not acquired:
        raise ApplicationError("schedule_busy", "Schedule update is in progress", status=503)


class ScheduleStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.fires = ScheduleFireStore(session_factory)

    def initialize(self) -> None:
        with self.session_factory() as session, session.begin():
            lock_identity(session, "platform-schema-initialization")
            PlatformBase.metadata.create_all(
                session.connection(),
                tables=[
                    cast(Table, ScheduleRow.__table__),
                    cast(Table, ScheduleTriggerRow.__table__),
                    cast(Table, ScheduleFireRow.__table__),
                ],
            )

    def list_fires(self, schedule_id: str, limit: int = 50) -> list[ScheduleFireRecord]:
        return self.fires.list(schedule_id, limit)

    @staticmethod
    def _record(row: ScheduleRow) -> ScheduleRecord:
        status = (
            "failed"
            if row.sync_error_code
            else (
                "pending"
                if row.revision != row.synced_revision
                else "deleted" if row.desired_deleted else "synced"
            )
        )
        return ScheduleRecord.model_validate(
            {
                **row.definition,
                "id": row.id,
                "revision": row.revision,
                "syncedRevision": row.synced_revision,
                "syncStatus": status,
                "syncErrorCode": row.sync_error_code,
                "desiredDeleted": row.desired_deleted,
                "updatedAt": row.updated_at,
            }
        )

    def save(
        self,
        definition: ScheduleDefinition,
        schedule_id: str | None = None,
        *,
        create_only: bool = False,
    ) -> ScheduleRecord:
        schedule_id = schedule_id or str(uuid4())
        with self.session_factory() as session, session.begin():
            _lock(session, schedule_id)
            row = session.get(ScheduleRow, schedule_id)
            payload = definition.model_dump(mode="json", by_alias=True)
            if row is None:
                row = ScheduleRow(
                    id=schedule_id,
                    definition=payload,
                    revision=1,
                    synced_revision=0,
                    desired_deleted=False,
                    updated_at=datetime.now(UTC),
                )
                session.add(row)
            elif create_only:
                if row.definition != payload:
                    raise ApplicationError(
                        "schedule_identity_conflict",
                        "This creation request already has different settings",
                        status=409,
                    )
            else:
                row.definition = payload
                row.revision += 1
                row.desired_deleted = False
                row.sync_error_code = None
                row.updated_at = datetime.now(UTC)
            return self._record(row)

    def get(self, schedule_id: str) -> ScheduleRecord | None:
        with self.session_factory() as session:
            row = session.get(ScheduleRow, schedule_id)
            return None if row is None else self._record(row)

    def list(self) -> list[ScheduleRecord]:
        with self.session_factory() as session:
            return [
                self._record(row)
                for row in session.scalars(select(ScheduleRow).order_by(ScheduleRow.id))
                if not (row.desired_deleted and row.revision == row.synced_revision)
            ]

    def pending(self) -> Sequence[ScheduleRecord]:
        with self.session_factory() as session:
            return [
                self._record(row)
                for row in session.scalars(
                    select(ScheduleRow).where(ScheduleRow.revision != ScheduleRow.synced_revision)
                )
            ]

    def mark_deleted(self, schedule_id: str) -> None:
        with self.session_factory() as session, session.begin():
            _lock(session, schedule_id)
            row = session.get(ScheduleRow, schedule_id)
            if row is None:
                raise ApplicationError("schedule_not_found", "Schedule is unavailable", status=404)
            if not row.desired_deleted:
                row.desired_deleted, row.sync_error_code = True, None
                row.revision += 1
                row.updated_at = datetime.now(UTC)

    async def synchronize(
        self, schedule_id: str, apply: Callable[[ScheduleRecord], Awaitable[None]]
    ) -> ScheduleRecord:
        error: ApplicationError | None = None
        with self.session_factory() as session, session.begin():
            _lock(session, schedule_id)
            row = session.get(ScheduleRow, schedule_id)
            if row is None:
                raise ApplicationError("schedule_not_found", "Schedule is unavailable", status=404)
            if row.revision != row.synced_revision:
                try:
                    await apply(self._record(row))
                except ApplicationError as exc:
                    error, row.sync_error_code = exc, exc.code
                else:
                    row.synced_revision, row.sync_error_code = row.revision, None
            result = self._record(row)
        if error is not None:
            raise error
        return result

    def request_trigger(self, schedule_id: str, trigger_id: str) -> ScheduleTriggerReceipt:
        with self.session_factory() as session, session.begin():
            _lock(session, schedule_id)
            schedule = session.get(ScheduleRow, schedule_id)
            if schedule is None or schedule.desired_deleted:
                raise ApplicationError("schedule_not_found", "Schedule is unavailable", status=404)
            row = session.get(ScheduleTriggerRow, (schedule_id, trigger_id))
            if row is None:
                previous = session.scalar(
                    select(func.min(ScheduleTriggerRow.identity_time)).where(
                        ScheduleTriggerRow.schedule_id == schedule_id
                    )
                )
                # The native scheduler truncates action identities to seconds. Reserve
                # past identity seconds for manual commands so simultaneous triggers do
                # not collide with one another or with current calendar actions.
                identity_time = (previous or datetime(1900, 1, 1, tzinfo=UTC)) - timedelta(
                    seconds=1
                )
                row = ScheduleTriggerRow(
                    schedule_id=schedule_id,
                    trigger_id=trigger_id,
                    identity_time=identity_time,
                    requested_at=datetime.now(UTC),
                )
                session.add(row)
            return self._receipt(row)

    def requested_time(self, schedule_id: str, identity_time: datetime) -> datetime | None:
        with self.session_factory() as session:
            return session.scalar(
                select(ScheduleTriggerRow.requested_at).where(
                    ScheduleTriggerRow.schedule_id == schedule_id,
                    ScheduleTriggerRow.identity_time == identity_time,
                )
            )

    @staticmethod
    def _receipt(row: ScheduleTriggerRow) -> ScheduleTriggerReceipt:
        return ScheduleTriggerReceipt(
            schedule_id=row.schedule_id,
            trigger_id=row.trigger_id,
            status="accepted" if row.delivered_at else "failed" if row.error_code else "pending",
            error_code=row.error_code,
        )

    def pending_triggers(self) -> Sequence[ScheduleTriggerReceipt]:
        with self.session_factory() as session:
            return [
                self._receipt(row)
                for row in session.scalars(
                    select(ScheduleTriggerRow).where(
                        ScheduleTriggerRow.delivered_at.is_(None),
                        ScheduleTriggerRow.error_code.is_distinct_from("schedule_deleted"),
                    )
                )
            ]

    async def deliver_trigger(
        self,
        schedule_id: str,
        trigger_id: str,
        send: Callable[[datetime], Awaitable[None]],
    ) -> ScheduleTriggerReceipt:
        error: ApplicationError | None = None
        with self.session_factory() as session, session.begin():
            _lock(session, schedule_id)
            row = session.get(ScheduleTriggerRow, (schedule_id, trigger_id))
            if row is None:
                raise ApplicationError("trigger_not_found", "Trigger is unavailable", status=404)
            schedule = session.get(ScheduleRow, schedule_id)
            if row.delivered_at is None:
                try:
                    if schedule is None or schedule.desired_deleted:
                        raise ApplicationError(
                            "schedule_deleted", "Schedule was deleted", status=409
                        )
                    if schedule.revision != schedule.synced_revision:
                        raise ApplicationError(
                            "schedule_pending", "Schedule is not synchronized", status=503
                        )
                    await send(row.identity_time)
                except ApplicationError as exc:
                    error, row.error_code = exc, exc.code
                else:
                    row.delivered_at, row.error_code = datetime.now(UTC), None
            result = self._receipt(row)
        if error is not None:
            raise error
        return result

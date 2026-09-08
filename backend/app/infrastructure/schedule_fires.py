"""Durable projections of accepted engine fires, including launch rejection evidence."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.domain.execution import ApplicationError
from app.domain.schedules import ScheduleFireRecord
from app.infrastructure.platform_models import CommandRow, PlatformBase, RunRow
from app.infrastructure.platform_transactions import lock_identity

_TERMINAL = {"launch_failed", "succeeded", "failed", "cancelled"}


class ScheduleFireRow(PlatformBase):
    __tablename__ = "platform_schedule_fires"
    trigger_id: Mapped[str] = mapped_column(String, primary_key=True)
    schedule_id: Mapped[str] = mapped_column(ForeignKey("platform_schedules.id"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    engine_workflow_id: Mapped[str] = mapped_column(String)
    engine_run_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("platform_runs.id"), unique=True)
    error_code: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScheduleFireStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def record(self, fire: ScheduleFireRecord) -> None:
        with self.sessions() as session, session.begin():
            lock_identity(session, "schedule-fire:" + fire.trigger_id)
            row = session.get(ScheduleFireRow, fire.trigger_id)
            if row is None:
                session.add(ScheduleFireRow(**fire.model_dump()))
                return
            # Keep the first execution link when the same logical fire is redelivered.
            for field in ("schedule_id", "scheduled_at", "engine_workflow_id"):
                if getattr(row, field) != getattr(fire, field):
                    raise ApplicationError(
                        "fire_identity_conflict", "Fire identity differs", status=409
                    )

    def launched_run(self, trigger_id: str) -> str | None:
        with self.sessions() as session:
            return session.scalar(
                select(RunRow.id).where(RunRow.launch_id == "schedule-fire:" + trigger_id)
            )

    def admission_failure(self, run_id: str) -> str | None:
        with self.sessions() as session:
            return session.scalar(
                select(CommandRow.rejection_code).where(CommandRow.id == "start:" + run_id)
            )

    def launched(self, trigger_id: str, run_id: str) -> None:
        with self.sessions() as session, session.begin():
            row = session.get(ScheduleFireRow, trigger_id, with_for_update=True)
            if row is None:
                raise ApplicationError("fire_not_found", "Fire evidence is unavailable", status=404)
            if row.run_id is not None and row.run_id != run_id:
                raise ApplicationError("fire_identity_conflict", "Fire Run differs", status=409)
            if row.status == "launch_failed":
                raise ApplicationError(
                    "fire_result_conflict", "Fire already failed launch", status=409
                )
            row.run_id = run_id
            if row.status not in _TERMINAL:
                row.status, row.updated_at = "launched", datetime.now(UTC)

    def launch_failed(self, trigger_id: str, error_code: str) -> None:
        with self.sessions() as session, session.begin():
            row = session.get(ScheduleFireRow, trigger_id, with_for_update=True)
            if row is None:
                raise ApplicationError("fire_not_found", "Fire evidence is unavailable", status=404)
            if row.status in _TERMINAL:
                if row.status != "launch_failed" or row.error_code != error_code:
                    raise ApplicationError(
                        "fire_result_conflict", "Fire result differs", status=409
                    )
                return
            row.status, row.error_code, row.updated_at = (
                "launch_failed",
                error_code,
                datetime.now(UTC),
            )

    def finished(self, run_id: str, status: str, error_code: str | None = None) -> None:
        if status not in {"succeeded", "failed", "cancelled"}:
            raise ApplicationError("fire_state_invalid", "Invalid terminal fire state")
        with self.sessions() as session, session.begin():
            row = session.scalar(
                select(ScheduleFireRow).where(ScheduleFireRow.run_id == run_id).with_for_update()
            )
            if row is None:
                raise ApplicationError("fire_not_found", "Fire evidence is unavailable", status=404)
            if row.status in _TERMINAL and (row.status, row.error_code) != (status, error_code):
                raise ApplicationError("fire_result_conflict", "Fire result differs", status=409)
            row.status, row.error_code, row.updated_at = status, error_code, datetime.now(UTC)

    def unfinished(self, limit: int = 100) -> list[ScheduleFireRecord]:
        with self.sessions() as session:
            rows = session.scalars(
                select(ScheduleFireRow)
                .where(ScheduleFireRow.status.in_(("pending", "launched")))
                .order_by(ScheduleFireRow.updated_at, ScheduleFireRow.trigger_id)
                .limit(limit)
            )
            return [ScheduleFireRecord.model_validate(row) for row in rows]

    def project_launch_failure(self, trigger_id: str, error_code: str) -> bool:
        with self.sessions() as session, session.begin():
            row = session.get(ScheduleFireRow, trigger_id, with_for_update=True)
            if row is None or row.status != "pending" or row.run_id is not None:
                return False
            row.status, row.error_code, row.updated_at = (
                "launch_failed",
                error_code,
                datetime.now(UTC),
            )
            return True

    def list(self, schedule_id: str, limit: int = 50) -> list[ScheduleFireRecord]:
        with self.sessions() as session:
            rows = session.scalars(
                select(ScheduleFireRow)
                .where(ScheduleFireRow.schedule_id == schedule_id)
                .order_by(ScheduleFireRow.scheduled_at.desc(), ScheduleFireRow.trigger_id)
                .limit(min(max(limit, 1), 200))
            )
            return [ScheduleFireRecord.model_validate(row) for row in rows]

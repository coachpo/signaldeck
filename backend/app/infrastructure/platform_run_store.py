"""Atomic launch outbox and engine-owned execution query projections."""

from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.application.effect_projection import unknown_evidence
from app.application.result_projection import run_title
from app.domain.execution import (
    ApplicationError,
    ExecutionEvidence,
    ResolvedRunSpec,
    RunDetail,
    RunStatus,
    RunSummary,
    StartCommand,
)
from app.domain.tool_contracts import canonical_digest
from app.infrastructure.evidence_payloads import persist_value
from app.infrastructure.platform_models import CommandRow, EvidenceRow, RunRow
from app.infrastructure.platform_projection_store import PlatformProjectionStore
from app.infrastructure.platform_transactions import lock_identity


class PlatformRunStore(PlatformProjectionStore):
    session_factory: sessionmaker[Session]

    @staticmethod
    def _summary(row: RunRow) -> RunSummary:
        return RunSummary.model_validate(
            dict(
                id=row.id,
                title=run_title(row.spec),
                package_key=row.spec["packageKey"],
                workflow_key=row.spec["workflowKey"],
                package_hash=row.spec["packageHash"],
                status=row.status,
                created_at=row.created_at,
                started_at=row.started_at,
                finished_at=row.finished_at,
                cancel_requested_at=row.cancel_requested_at,
                origin=row.spec["origin"],
            )
        )

    def create_run(self, spec: ResolvedRunSpec, launch_id: str) -> RunSummary:
        payload = spec.model_dump(mode="json", by_alias=True)
        intent = {
            key: payload[key] for key in ("packageKey", "workflowKey", "parameters", "origin")
        }
        digest = canonical_digest(intent)
        with self.session_factory() as session, session.begin():
            lock_identity(session, "launch:" + launch_id)
            existing = session.scalar(select(RunRow).where(RunRow.launch_id == launch_id))
            if existing is not None:
                if existing.launch_digest != digest:
                    raise ApplicationError(
                        "launch_identity_conflict",
                        "Launch identity has different input",
                        status=409,
                    )
                return self._summary(existing)
            lock_identity(session, "run:" + spec.run_id)
            if session.get(RunRow, spec.run_id) is not None:
                raise ApplicationError(
                    "run_identity_conflict", "Run identity already exists", status=409
                )
            now = datetime.now(UTC)
            row = RunRow(
                id=spec.run_id,
                launch_id=launch_id,
                launch_digest=digest,
                spec=payload,
                status="queued",
                created_at=now,
            )
            session.add(row)
            session.flush()
            session.add(
                CommandRow(
                    id="start:" + spec.run_id,
                    run_id=spec.run_id,
                    kind="start",
                    attempts=0,
                    created_at=now,
                )
            )
            return self._summary(row)

    def get_run_by_launch_id(self, launch_id: str) -> RunDetail | None:
        with self.session_factory() as session:
            run_id = session.scalar(select(RunRow.id).where(RunRow.launch_id == launch_id))
        return None if run_id is None else self.get_run(run_id)

    def get_run(self, run_id: str) -> RunDetail | None:
        with self.session_factory() as session:
            row = session.get(RunRow, run_id)
            if row is None:
                return None
            evidence = session.scalars(
                select(EvidenceRow).where(EvidenceRow.run_id == run_id).order_by(EvidenceRow.id)
            ).all()
            summary = self._summary(row)
            writes, reads = unknown_evidence(row.spec, [item.payload for item in evidence])
            summary.has_unknown_effects = bool(writes)
            summary.has_unknown_results = bool(reads)
            return RunDetail(
                **summary.model_dump(),
                spec=ResolvedRunSpec.model_validate(row.spec),
                output=deepcopy(row.output),
                error_code=row.error_code,
                evidence=[ExecutionEvidence.model_validate(item.payload) for item in evidence],
            )

    def list_runs(self) -> list[RunSummary]:
        with self.session_factory() as session:
            return [
                self._summary(row)
                for row in session.scalars(
                    select(RunRow).order_by(RunRow.created_at.desc(), RunRow.id)
                )
            ]

    def pending_commands(self, limit: int = 100) -> list[StartCommand]:
        """Delivery only: the execution engine owns scheduling and retries."""
        with self.session_factory() as session:
            rows = session.scalars(
                select(CommandRow)
                .where(CommandRow.delivered_at.is_(None))
                .order_by(CommandRow.created_at, CommandRow.id)
                .limit(limit)
            )
            return [
                StartCommand.model_validate(
                    dict(
                        id=row.id,
                        run_id=row.run_id,
                        kind=row.kind,
                        attempts=row.attempts,
                        created_at=row.created_at,
                    )
                )
                for row in rows
            ]

    def acknowledge_command(self, command_id: str) -> None:
        with self.session_factory() as session, session.begin():
            row = session.get(CommandRow, command_id, with_for_update=True)
            if row is None:
                raise ApplicationError("command_not_found", "Command is unavailable", status=404)
            if row.delivered_at is None:
                row.delivered_at = datetime.now(UTC)

    def note_command_attempt(self, command_id: str) -> None:
        with self.session_factory() as session, session.begin():
            row = session.get(CommandRow, command_id, with_for_update=True)
            if row is None:
                raise ApplicationError("command_not_found", "Command is unavailable", status=404)
            row.attempts += 1

    def request_cancel(self, run_id: str) -> RunSummary:
        with self.session_factory() as session, session.begin():
            row = session.get(RunRow, run_id, with_for_update=True)
            if row is None:
                raise ApplicationError("run_not_found", "Run is unavailable", status=404)
            if (
                row.status not in {"succeeded", "failed", "cancelled", "timed_out"}
                and row.cancel_requested_at is None
            ):
                row.cancel_requested_at = datetime.now(UTC)
                session.add(
                    CommandRow(
                        id="cancel:" + run_id,
                        run_id=run_id,
                        kind="cancel",
                        attempts=0,
                        created_at=row.cancel_requested_at,
                    )
                )
            return self._summary(row)

    def project_run(
        self, run_id: str, status: RunStatus, output: Any = None, error_code: str | None = None
    ) -> None:
        """Consume an engine fact; never create execution work from a projection."""
        output = persist_value(output, self.artifacts)
        with self.session_factory() as session, session.begin():
            row = session.get(RunRow, run_id, with_for_update=True)
            if row is None:
                raise ApplicationError("run_not_found", "Run is unavailable", status=404)
            if row.status in {"succeeded", "failed", "cancelled", "timed_out"}:
                if (row.status, row.output, row.error_code) != (status, output, error_code):
                    raise ApplicationError(
                        "run_result_conflict", "Terminal run result is immutable", status=409
                    )
                return
            if row.status == "running" and status == "queued":
                raise ApplicationError(
                    "run_state_conflict", "Run cannot return to queued", status=409
                )
            now = datetime.now(UTC)
            row.status, row.output, row.error_code = status, deepcopy(output), error_code
            if status == "running" and row.started_at is None:
                row.started_at = now
            if status in {"succeeded", "failed", "cancelled", "timed_out"}:
                row.finished_at = now

    @contextmanager
    def command_delivery(self, command_id: str) -> Iterator[bool]:
        """Serialize one outbox delivery; a busy command waits for the next delivery pass."""
        with self.session_factory() as session, session.begin():
            acquired = session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:identity, 0))"),
                {"identity": "command-delivery:" + command_id},
            )
            if not acquired:
                yield False
                return
            command = session.get(CommandRow, command_id)
            yield command is not None and command.delivered_at is None

    def reject_run_admission(self, command_id: str, error_code: str) -> None:
        """Record a definite pre-engine admission rejection with its outbox acknowledgement."""
        with self.session_factory() as session, session.begin():
            command = session.get(CommandRow, command_id, with_for_update=True)
            if command is None or command.kind != "start" or command.delivered_at is not None:
                return
            row = session.get(RunRow, command.run_id, with_for_update=True)
            assert row is not None
            now = datetime.now(UTC)
            if row.status == "queued":
                row.status, row.error_code, row.finished_at = "failed", error_code, now
                command.rejection_code = error_code
            command.delivered_at = now

    def command_rejection(self, command_id: str) -> str | None:
        """Return the immutable pre-engine rejection receipt, independent of run projection."""
        with self.session_factory() as session:
            return session.scalar(
                select(CommandRow.rejection_code).where(CommandRow.id == command_id)
            )

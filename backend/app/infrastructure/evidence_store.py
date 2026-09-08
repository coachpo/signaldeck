"""Immutable execution evidence and durable tool-operation recovery records."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.execution import ApplicationError, ExecutionEvidence
from app.domain.tool_contracts import ToolOperationRecord, ToolResult
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.evidence_payloads import execution_value, persist_value
from app.infrastructure.evidence_records import EvidenceStore as EvidenceStore
from app.infrastructure.evidence_records import save_evidence
from app.infrastructure.platform_models import EvidenceRow, OperationRow
from app.infrastructure.platform_transactions import lock_identity


async def _settle_guard_io[T](task: asyncio.Task[T]) -> tuple[T, bool]:
    """Finish a short DB operation even if its awaiting caller is cancelled again."""
    cancelled = False
    while True:
        try:
            return await asyncio.shield(task), cancelled
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True


class PostgresToolEvidenceStore:
    """Async gateway port backed by the same evidence tree used in run reads."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifacts: ArtifactStore | None = None,
        *,
        operation_concurrency: int = 4,
    ):
        if operation_concurrency < 1:
            raise ValueError("Operation guard concurrency must be positive")
        self.session_factory = session_factory
        self.artifacts = artifacts
        # Detached lock connections do not consume the ordinary evidence pool, but
        # still consume PostgreSQL connections. Admission waits on the event loop.
        self._operation_slots = asyncio.Semaphore(operation_concurrency)

    @asynccontextmanager
    async def operation_guard(self, operation_id: str, deadline: datetime) -> AsyncIterator[bool]:
        if deadline.tzinfo is None:
            raise ValueError("Operation deadline must include a timezone")
        if self._operation_slots.locked():
            remaining = (deadline - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                yield False
                return
            try:
                async with asyncio.timeout(remaining):
                    await self._operation_slots.acquire()
            except TimeoutError:
                yield False
                return
        else:
            # An immediate ownership attempt permits the existing expired-result
            # path to reserve/read evidence without scheduling any external I/O.
            await self._operation_slots.acquire()
        connection = None
        close_cancelled = False
        try:
            connection, cancelled = await _settle_guard_io(
                asyncio.create_task(asyncio.to_thread(self._acquire_operation_guard, operation_id))
            )
            if cancelled:
                raise asyncio.CancelledError
            yield connection is not None
        finally:
            try:
                if connection is not None:
                    _, close_cancelled = await _settle_guard_io(
                        asyncio.create_task(asyncio.to_thread(connection.close))
                    )
            finally:
                self._operation_slots.release()
            if close_cancelled:
                raise asyncio.CancelledError

    def _acquire_operation_guard(self, operation_id: str) -> Connection | None:
        # Resolve the bind in a short, thread-local Session; no Session is kept
        # alive or shared while the gateway performs asynchronous external I/O.
        with self.session_factory() as session:
            bind = session.get_bind()
            engine = bind if isinstance(bind, Engine) else bind.engine
        connection = engine.connect()
        try:
            connection = connection.execution_options(isolation_level="AUTOCOMMIT")
            connection.detach()
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                {"key": "tool-operation:" + operation_id},
            )
            if acquired:
                return connection
        except BaseException:
            connection.close()
            raise
        connection.close()
        return None

    async def get_operation(self, operation_id: str) -> ToolOperationRecord | None:
        return await asyncio.to_thread(self._get_operation, operation_id)

    def _get_operation(self, operation_id: str) -> ToolOperationRecord | None:
        with self.session_factory() as session:
            row = session.get(OperationRow, operation_id)
            return None if row is None else self._decode_operation(row.payload)

    async def count_execute_attempts(self, operation_id: str) -> int:
        return await asyncio.to_thread(self._count_execute_attempts, operation_id)

    def _count_execute_attempts(self, operation_id: str) -> int:
        with self.session_factory() as session:
            return (
                session.scalar(
                    select(func.count())
                    .select_from(EvidenceRow)
                    .where(
                        EvidenceRow.parent_id == operation_id,
                        EvidenceRow.payload["kind"].as_string() == "attempt",
                        EvidenceRow.payload["metadata"]["networkKind"].as_string() == "execute",
                    )
                )
                or 0
            )

    async def reserve_operation(self, operation: ToolOperationRecord) -> bool:
        return await asyncio.to_thread(self._reserve_operation, operation)

    def _reserve_operation(self, operation: ToolOperationRecord) -> bool:
        context = operation.context
        with self.session_factory() as session, session.begin():
            lock_identity(session, "evidence:" + context.operation_id)
            if session.get(OperationRow, context.operation_id) is not None:
                return False
            if (
                operation.status != "pending"
                or operation.attempts != 0
                or operation.result is not None
            ):
                raise ApplicationError(
                    "operation_initial_state_invalid", "Operation must start pending", status=409
                )
            save_evidence(
                session,
                ExecutionEvidence(
                    id=context.operation_id,
                    run_id=context.run_id,
                    parent_id=context.invocation_id,
                    node_id=context.node_id,
                    kind="tool",
                    status="pending",
                    operation_id=context.operation_id,
                    tool_id=operation.tool_id,
                    input=operation.arguments,
                    metadata={"inputDigest": operation.input_digest},
                ),
                self.artifacts,
            )
            session.flush()
            session.add(
                OperationRow(
                    id=context.operation_id,
                    payload=self._encode_operation(operation),
                )
            )
            return True

    async def begin_attempt(self, operation_id: str, kind: str) -> int:
        return await asyncio.to_thread(self._begin_attempt, operation_id, kind)

    def _begin_attempt(self, operation_id: str, kind: str) -> int:
        if kind not in {"execute", "query", "cache_validation"}:
            raise ApplicationError(
                "attempt_kind_invalid", "Unsupported network attempt", status=400
            )
        with self.session_factory() as session, session.begin():
            row, operation = self._locked_operation(session, operation_id)
            if operation.status == "succeeded":
                raise ApplicationError(
                    "operation_already_confirmed",
                    "Successful operation cannot be attempted",
                    status=409,
                )
            attempt = operation.attempts + 1
            row.payload = self._encode_operation(
                operation.model_copy(update={"attempts": attempt, "status": "unknown"})
            )
            context = operation.context
            save_evidence(
                session,
                ExecutionEvidence(
                    id=f"{operation_id}:attempt:{attempt}",
                    run_id=context.run_id,
                    parent_id=operation_id,
                    node_id=context.node_id,
                    kind="attempt",
                    status="running",
                    attempt=attempt,
                    operation_id=operation_id,
                    tool_id=operation.tool_id,
                    started_at=datetime.now(UTC),
                    metadata={"networkKind": kind},
                    input=(
                        operation.arguments
                        if kind == "execute"
                        else (
                            {"toolId": operation.tool_id}
                            if kind == "cache_validation"
                            else {"operationId": operation_id}
                        )
                    ),
                ),
                self.artifacts,
            )
            evidence = session.get(EvidenceRow, operation_id)
            assert evidence is not None
            evidence.payload = {**evidence.payload, "status": "unknown"}
            return attempt

    async def finish_attempt(self, operation_id: str, attempt: int, result: ToolResult) -> None:
        await asyncio.to_thread(self._finish_attempt, operation_id, attempt, result)

    def _finish_attempt(self, operation_id: str, attempt: int, result: ToolResult) -> None:
        with self.session_factory() as session, session.begin():
            operation_row, operation = self._locked_operation(session, operation_id)
            row = session.get(EvidenceRow, f"{operation_id}:attempt:{attempt}")
            if row is None:
                raise ApplicationError("attempt_not_found", "Attempt is unavailable", status=404)
            evidence = ExecutionEvidence.model_validate(row.payload)
            status = "failed" if result.status == "not_found" else result.status
            updated = evidence.model_copy(
                update={
                    "status": status,
                    "output": deepcopy(result.output),
                    "error_code": result.code,
                    "finished_at": datetime.now(UTC),
                    "metadata": {
                        **evidence.metadata,
                        "resultStatus": result.status,
                        "retryable": result.retryable,
                        "cacheProvenance": (
                            result.cache_provenance.model_dump(mode="json", by_alias=True)
                            if result.cache_provenance is not None
                            else None
                        ),
                    },
                }
            )
            save_evidence(session, updated, self.artifacts)
            if (
                result.status == "succeeded"
                and evidence.metadata.get("networkKind") != "cache_validation"
            ):
                # The confirmed network result and reusable operation result commit together.
                self._save_operation_result(session, operation_row, operation, result)

    async def finish_operation(self, operation_id: str, result: ToolResult) -> None:
        await asyncio.to_thread(self._finish_operation, operation_id, result)

    def _finish_operation(self, operation_id: str, result: ToolResult) -> None:
        with self.session_factory() as session, session.begin():
            row, operation = self._locked_operation(session, operation_id)
            self._save_operation_result(session, row, operation, result)

    def _save_operation_result(
        self,
        session: Session,
        row: OperationRow,
        operation: ToolOperationRecord,
        result: ToolResult,
    ) -> None:
        if operation.status == "succeeded":
            if operation.result != result:
                raise ApplicationError(
                    "operation_result_conflict", "Successful operation is immutable", status=409
                )
            return
        status = "unknown" if result.status == "not_found" else result.status
        row.payload = self._encode_operation(
            operation.model_copy(update={"status": status, "result": result})
        )
        evidence_row = session.get(EvidenceRow, operation.context.operation_id)
        assert evidence_row is not None
        evidence = ExecutionEvidence.model_validate(evidence_row.payload)
        # A retryable failure is still unresolved at the logical operation boundary.
        evidence_status = "unknown" if result.retryable and status == "failed" else status
        save_evidence(
            session,
            evidence.model_copy(
                update={
                    "status": evidence_status,
                    "output": deepcopy(result.output),
                    "error_code": result.code,
                    "finished_at": datetime.now(UTC),
                    "metadata": {
                        **evidence.metadata,
                        "retryable": result.retryable,
                        "cacheProvenance": (
                            result.cache_provenance.model_dump(mode="json", by_alias=True)
                            if result.cache_provenance is not None
                            else None
                        ),
                    },
                }
            ),
            self.artifacts,
        )

    def _locked_operation(
        self, session: Session, operation_id: str
    ) -> tuple[OperationRow, ToolOperationRecord]:
        lock_identity(session, "evidence:" + operation_id)
        row = session.get(OperationRow, operation_id)
        if row is None:
            raise ApplicationError("operation_not_found", "Operation is unavailable", status=404)
        return row, self._decode_operation(row.payload)

    def _encode_operation(self, operation: ToolOperationRecord) -> dict[str, Any]:
        payload = operation.model_dump(mode="json", by_alias=True)
        payload["arguments"] = persist_value(payload["arguments"], self.artifacts)
        if payload["result"] is not None:
            payload["result"]["output"] = persist_value(payload["result"]["output"], self.artifacts)
        return payload

    def _decode_operation(self, stored: dict[str, Any]) -> ToolOperationRecord:
        payload = deepcopy(stored)
        payload["arguments"] = execution_value(payload["arguments"], self.artifacts)
        if payload["result"] is not None:
            payload["result"]["output"] = execution_value(
                payload["result"]["output"], self.artifacts
            )
        return ToolOperationRecord.model_validate(payload)

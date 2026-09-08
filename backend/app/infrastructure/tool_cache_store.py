"""PostgreSQL read-cache references to immutable confirmed tool-operation results."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, String, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.domain.tool_contracts import ToolCacheProvenance, ToolResult
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.evidence_payloads import execution_value
from app.infrastructure.platform_models import OperationRow
from app.infrastructure.platform_transactions import lock_identity


class ToolCacheBase(DeclarativeBase):
    pass


class ToolCacheRow(ToolCacheBase):
    __tablename__ = "platform_read_tool_cache"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    source_operation_id: Mapped[str] = mapped_column(ForeignKey(OperationRow.id))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PostgresToolCacheStore:
    def __init__(
        self, session_factory: sessionmaker[Session], artifacts: ArtifactStore | None = None
    ):
        self.session_factory = session_factory
        self.artifacts = artifacts

    def initialize(self) -> None:
        with self.session_factory() as session, session.begin():
            lock_identity(session, "read-tool-cache-schema")
            ToolCacheBase.metadata.create_all(session.connection())

    async def get(self, key: str, ttl_seconds: int, requesting_run_id: str) -> ToolResult | None:
        return await asyncio.to_thread(self._get, key, ttl_seconds, requesting_run_id)

    def _get(self, key: str, ttl_seconds: int, requesting_run_id: str) -> ToolResult | None:
        with self.session_factory() as session:
            row = session.get(ToolCacheRow, key)
            if row is None:
                return None
            now = session.scalar(select(text("clock_timestamp()")))
            expires_at = min(row.expires_at, row.fetched_at + timedelta(seconds=ttl_seconds))
            if expires_at <= now:
                return None
            source = self._source(session, row.source_operation_id, key)
            if source.source_run_id == requesting_run_id:
                return None
            operation = session.get(OperationRow, row.source_operation_id)
            assert operation is not None
            output = execution_value(operation.payload["result"]["output"], self.artifacts)
            return ToolResult(
                status="succeeded",
                output=output,
                cache_provenance=source.model_copy(update={"hit": True, "expires_at": expires_at}),
            )

    async def put(self, key: str, source_operation_id: str) -> None:
        await asyncio.to_thread(self._put, key, source_operation_id)

    def _put(self, key: str, source_operation_id: str) -> None:
        with self.session_factory() as session, session.begin():
            lock_identity(session, "read-tool-cache:" + key)
            provenance = self._source(session, source_operation_id, key)
            row = session.get(ToolCacheRow, key)
            if row is not None and row.fetched_at >= provenance.fetched_at:
                return
            if row is None:
                session.add(
                    ToolCacheRow(
                        key=key,
                        source_operation_id=source_operation_id,
                        fetched_at=provenance.fetched_at,
                        expires_at=provenance.expires_at,
                    )
                )
            else:
                row.source_operation_id = source_operation_id
                row.fetched_at = provenance.fetched_at
                row.expires_at = provenance.expires_at

    @staticmethod
    def _source(session: Session, operation_id: str, key: str) -> ToolCacheProvenance:
        operation = session.get(OperationRow, operation_id)
        if operation is None or operation.payload.get("effect") != "read":
            raise ValueError("Cache source must be a confirmed read operation")
        payload = operation.payload
        result = payload.get("result")
        if payload["status"] != "succeeded" or result is None or result["status"] != "succeeded":
            raise ValueError("Cache source must be a confirmed read operation")
        context = payload["context"]
        provenance = ToolCacheProvenance.model_validate(result.get("cacheProvenance"))
        if (
            context.get("cachePolicy") is None
            or provenance.hit
            or provenance.cache_key != key
            or provenance.source_operation_id != operation_id
            or provenance.source_run_id != context["runId"]
        ):
            raise ValueError("Cache source policy or identity differs")
        return provenance

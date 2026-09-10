"""Explicit annotation writes with optimistic concurrency, without execution effects."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.execution import ApplicationError
from app.infrastructure.platform_models import PlatformBase, RunRow
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.platform_transactions import lock_identity
from app.schemas.result_metadata import ResultMetadataPatch, ResultMetadataRead


class ResultMetadataRow(PlatformBase):
    __tablename__ = "platform_result_metadata"
    run_id: Mapped[str] = mapped_column(ForeignKey(RunRow.id), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    is_favorite: Mapped[bool] = mapped_column(Boolean)
    is_read: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AttentionReceiptRow(PlatformBase):
    __tablename__ = "platform_attention_receipts"
    identity: Mapped[str] = mapped_column(String, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    is_read: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResultMetadataStore:
    def __init__(self, platform: PlatformStore):
        self.platform = platform

    def read_many(self, run_ids: list[str]) -> dict[str, ResultMetadataRead]:
        with self.platform.session_factory() as session:
            return {
                row.run_id: ResultMetadataRead.model_validate(row)
                for row in session.scalars(
                    select(ResultMetadataRow).where(ResultMetadataRow.run_id.in_(run_ids))
                )
            }

    def get(self, run_id: str) -> ResultMetadataRead:
        with self.platform.session_factory() as session:
            if session.get(RunRow, run_id) is None:
                raise ApplicationError("run_not_found", "Run is unavailable", status=404)
            row = session.get(ResultMetadataRow, run_id)
            return (
                ResultMetadataRead(run_id=run_id)
                if row is None
                else ResultMetadataRead.model_validate(row)
            )

    def patch(self, run_id: str, payload: ResultMetadataPatch) -> ResultMetadataRead:
        from app.infrastructure.attention_store import AttentionStore

        # A read command acknowledges only the observed state, never a later change.
        observed = (
            next(
                (
                    item
                    for item in AttentionStore(self.platform)._items(datetime.now(UTC))
                    if item.run_id == run_id
                ),
                None,
            )
            if payload.is_read is True
            else None
        )
        with self.platform.session_factory() as session, session.begin():
            lock_identity(session, "result-metadata:" + run_id)
            if session.get(RunRow, run_id) is None:
                raise ApplicationError("run_not_found", "Run is unavailable", status=404)
            row = session.get(ResultMetadataRow, run_id)
            revision = 0 if row is None else row.revision
            if payload.expected_revision != revision:
                raise ApplicationError(
                    "result_metadata_conflict",
                    "Result annotations changed; reload before saving your changes",
                    status=409,
                )
            if row is None:
                row = ResultMetadataRow(
                    run_id=run_id, revision=0, is_favorite=False, is_read=False, note=""
                )
                session.add(row)
            for field in payload.model_fields_set - {"expected_revision"}:
                setattr(row, field, getattr(payload, field))
            row.revision += 1
            row.updated_at = datetime.now(UTC)
            if observed is not None:
                lock_identity(session, "attention-read:" + observed.id)
                receipt = session.get(AttentionReceiptRow, observed.id)
                if receipt is None:
                    receipt = AttentionReceiptRow(identity=observed.id, revision=0)
                    session.add(receipt)
                receipt.revision += 1
                receipt.is_read = True
                receipt.updated_at = row.updated_at
            return ResultMetadataRead.model_validate(row)

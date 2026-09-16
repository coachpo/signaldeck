"""Finance-owned immutable observations and monotonically advancing baseline pointers."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ResearchSnapshot(Base):
    __tablename__ = "research_monitor_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    monitor_key: Mapped[str] = mapped_column(String(160), index=True)
    scope_hash: Mapped[str] = mapped_column(String(71), index=True)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scope: Mapped[dict] = mapped_column(JSONB)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    observation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    previous_snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    run_id: Mapped[str] = mapped_column(String(200))
    report_status: Mapped[str] = mapped_column(String(20), default="pending")
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    report_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)


class ResearchHead(Base):
    __tablename__ = "research_monitor_heads"

    monitor_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    scope_hash: Mapped[str] = mapped_column(String(71), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(36))
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

from __future__ import annotations

from finance_plugin.models.base import Base, IdMixin, TimestampMixin
from sqlalchemy import CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

REPORT_SOURCE_VALUES = ("compiled", "uploaded", "external", "agent")
REPORT_SOURCE_CHECK_CONSTRAINT = "ck_reports_source"
REPORT_SOURCE_CHECK_SQL = "source IN ('compiled', 'uploaded', 'external', 'agent')"


class Report(IdMixin, TimestampMixin, Base):
    __tablename__: str = "reports"
    __table_args__: tuple[UniqueConstraint, UniqueConstraint, CheckConstraint] = (
        UniqueConstraint("name", name="uq_reports_name"),
        UniqueConstraint("slug", name="uq_reports_slug"),
        CheckConstraint(REPORT_SOURCE_CHECK_SQL, name=REPORT_SOURCE_CHECK_CONSTRAINT),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="compiled")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )

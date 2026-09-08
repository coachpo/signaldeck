from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from finance_plugin.models.base import Base, IdMixin
from plugin_runtime.formatting import utcnow
from sqlalchemy import Boolean, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class MarketQuote(IdMixin, Base):
    __tablename__ = "market_quotes"
    __table_args__ = (
        UniqueConstraint(
            "provider", "symbol", "as_of", name="uq_market_quotes_provider_symbol_as_of"
        ),
        Index("ix_market_quotes_symbol_fetched_at", "symbol", "fetched_at"),
        Index("ix_market_quotes_provider_symbol", "provider", "symbol"),
    )

    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    previous_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

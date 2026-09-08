from __future__ import annotations

from datetime import datetime

from finance_plugin.models.market_quote import MarketQuote
from sqlalchemy import desc, select
from sqlalchemy.orm import Session


class MarketQuoteRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_latest(self, symbol: str) -> MarketQuote | None:
        statement = (
            select(MarketQuote)
            .where(MarketQuote.symbol == symbol)
            .order_by(desc(MarketQuote.fetched_at))
            .limit(1)
        )
        return self.session.scalar(statement)

    def get_by_provider_symbol_as_of(
        self, provider: str, symbol: str, as_of: datetime | None
    ) -> MarketQuote | None:
        statement = select(MarketQuote).where(
            MarketQuote.provider == provider,
            MarketQuote.symbol == symbol,
            MarketQuote.as_of == as_of,
        )
        return self.session.scalar(statement)

    def add(self, quote: MarketQuote) -> MarketQuote:
        self.session.add(quote)
        return quote

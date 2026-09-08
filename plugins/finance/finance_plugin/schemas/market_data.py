from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from plugin_runtime.common import CamelModel


class MarketQuoteRead(CamelModel):
    symbol: str
    name: str | None = None
    price: Decimal
    currency: str
    provider: str
    as_of: datetime | None
    is_stale: bool
    previous_close: Decimal | None = None


class MarketQuoteListRead(CamelModel):
    quotes: list[MarketQuoteRead]
    warnings: list[str]


class MarketHistoryPointRead(CamelModel):
    at: datetime
    close: Decimal


class MarketHistorySeriesRead(CamelModel):
    symbol: str
    currency: str | None = None
    provider: str
    points: list[MarketHistoryPointRead]


class MarketHistoryRead(CamelModel):
    range: str
    interval: str
    series: list[MarketHistorySeriesRead]
    warnings: list[str]

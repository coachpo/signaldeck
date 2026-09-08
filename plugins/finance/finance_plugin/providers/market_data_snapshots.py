from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from finance_plugin.contracts import RuntimeToolWarning
from finance_plugin.schemas.market_data import MarketHistorySeriesRead, MarketQuoteRead
from plugin_runtime.common import CamelModel, ensure_timezone
from pydantic import Field, field_validator, model_validator


def _validate_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_timezone(value)


def _validate_chronological_datetimes(rows: Sequence[datetime]) -> None:
    previous: datetime | None = None
    for current in rows:
        if previous is not None and current < previous:
            raise ValueError("Rows must be chronological")
        previous = current


class MarketDataQuoteLookupResult(CamelModel):
    quotes: list[MarketQuoteRead]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class MarketDataHistoryLookupResult(CamelModel):
    range: str
    interval: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    series: list[MarketHistorySeriesRead]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_bounds(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)

    @model_validator(mode="after")
    def validate_date_bounds(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("startDate must be before or equal to endDate")
        return self


class MarketDataOhlcvRow(CamelModel):
    at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = Field(default=None, ge=0)
    adjusted_close: Decimal | None = None

    @field_validator("at")
    @classmethod
    def validate_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MarketDataOhlcvSeries(CamelModel):
    symbol: str
    currency: str | None = None
    provider: str
    rows: list[MarketDataOhlcvRow]

    @model_validator(mode="after")
    def validate_rows(self) -> Self:
        _validate_chronological_datetimes([row.at for row in self.rows])
        if any(row.high < row.low for row in self.rows):
            raise ValueError("OHLCV high must be greater than or equal to low")
        return self


class MarketDataOhlcvLookupResult(CamelModel):
    start_date: datetime
    end_date: datetime
    series: list[MarketDataOhlcvSeries]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_bounds(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @model_validator(mode="after")
    def validate_date_bounds(self) -> Self:
        if self.start_date > self.end_date:
            raise ValueError("startDate must be before or equal to endDate")
        return self


class MarketDataIndicatorValue(CamelModel):
    name: str
    value: Decimal | None
    null_reason: Literal["warmup", "insufficient_history", "provider_gap"] | None = None

    @model_validator(mode="after")
    def validate_null_reason(self) -> Self:
        if self.value is None and self.null_reason is None:
            raise ValueError("nullReason is required when value is null")
        if self.value is not None and self.null_reason is not None:
            raise ValueError("nullReason must be null when value is present")
        return self


class MarketDataIndicatorRow(CamelModel):
    at: datetime
    values: list[MarketDataIndicatorValue]

    @field_validator("at")
    @classmethod
    def validate_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MarketDataIndicatorLookupResult(CamelModel):
    symbol: str
    provider: str
    current_date: datetime
    start_date: datetime
    end_date: datetime
    rows: list[MarketDataIndicatorRow]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("current_date", "start_date", "end_date")
    @classmethod
    def validate_dates(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @model_validator(mode="after")
    def validate_chronological_rows(self) -> Self:
        if self.start_date > self.end_date:
            raise ValueError("startDate must be before or equal to endDate")
        if self.end_date > self.current_date:
            raise ValueError("endDate cannot be after currentDate")
        _validate_chronological_datetimes([row.at for row in self.rows])
        for row in self.rows:
            if row.at < self.start_date or row.at > self.end_date:
                raise ValueError("Indicator rows must be within startDate and endDate")
        return self


class MarketDataFundamentalMetric(CamelModel):
    name: str
    value: Decimal | str | None
    currency: str | None = None
    period: str | None = None
    as_of: datetime | None = None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class MarketDataFinancialStatementLine(CamelModel):
    name: str
    value: Decimal | None
    currency: str | None = None


class MarketDataFinancialStatement(CamelModel):
    statement_type: Literal["income_statement", "balance_sheet", "cash_flow"]
    period: Literal["annual", "quarterly", "trailing_twelve_months"]
    period_end: datetime
    lines: list[MarketDataFinancialStatementLine]

    @field_validator("period_end")
    @classmethod
    def validate_period_end(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MarketDataFundamentalsLookupResult(CamelModel):
    symbol: str
    provider: str
    as_of: datetime
    metrics: list[MarketDataFundamentalMetric] = Field(default_factory=list)
    statements: list[MarketDataFinancialStatement] = Field(default_factory=list)
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MarketDataNewsItem(CamelModel):
    title: str
    url: str | None = None
    source: str
    published_at: datetime
    summary: str | None = None
    symbols: list[str] = Field(default_factory=list)
    sentiment: Literal["positive", "neutral", "negative", "mixed"] | None = None

    @field_validator("published_at")
    @classmethod
    def validate_published_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MarketDataNewsLookupResult(CamelModel):
    query: str | None = None
    symbols: list[str] = Field(default_factory=list)
    start_date: datetime | None = None
    end_date: datetime | None = None
    items: list[MarketDataNewsItem]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_bounds(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class MarketDataInsiderTransaction(CamelModel):
    insider_name: str
    role: str | None = None
    transaction_type: str
    shares: Decimal | None = None
    price: Decimal | None = None
    value: Decimal | None = None
    filed_at: datetime | None = None
    transaction_date: datetime

    @field_validator("filed_at", "transaction_date")
    @classmethod
    def validate_dates(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class MarketDataInsiderDataLookupResult(CamelModel):
    symbol: str
    provider: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    transactions: list[MarketDataInsiderTransaction]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_bounds(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


__all__ = [
    "MarketDataFinancialStatement",
    "MarketDataFinancialStatementLine",
    "MarketDataFundamentalMetric",
    "MarketDataFundamentalsLookupResult",
    "MarketDataHistoryLookupResult",
    "MarketDataIndicatorLookupResult",
    "MarketDataIndicatorRow",
    "MarketDataIndicatorValue",
    "MarketDataInsiderDataLookupResult",
    "MarketDataInsiderTransaction",
    "MarketDataNewsItem",
    "MarketDataNewsLookupResult",
    "MarketDataOhlcvLookupResult",
    "MarketDataOhlcvRow",
    "MarketDataOhlcvSeries",
    "MarketDataQuoteLookupResult",
]

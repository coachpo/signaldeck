# ruff: noqa: I001
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Self

from finance_plugin.contracts import RuntimeToolWarning
from finance_plugin.providers.market_data_snapshots import (
    MarketDataFinancialStatement as RuntimeFinancialStatement,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataFinancialStatementLine as RuntimeFinancialStatementLine,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataFundamentalMetric as RuntimeFundamentalMetric,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataFundamentalsLookupResult,
    MarketDataIndicatorLookupResult,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataIndicatorRow as RuntimeIndicatorRow,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataIndicatorValue as RuntimeIndicatorValue,
)
from finance_plugin.providers.market_data_snapshots import MarketDataInsiderDataLookupResult
from finance_plugin.providers.market_data_snapshots import (
    MarketDataInsiderTransaction as RuntimeInsiderTransaction,
)
from finance_plugin.providers.market_data_snapshots import MarketDataNewsItem as RuntimeNewsItem
from finance_plugin.providers.market_data_snapshots import (
    MarketDataNewsLookupResult,
    MarketDataOhlcvLookupResult,
)
from finance_plugin.providers.market_data_snapshots import MarketDataOhlcvRow as RuntimeOhlcvRow
from finance_plugin.providers.market_data_snapshots import (
    MarketDataOhlcvSeries as RuntimeOhlcvSeries,
)
from finance_plugin.providers.social_sentiment_snapshots import SocialSentimentLookupResult
from finance_plugin.providers.social_sentiment_snapshots import (
    SocialSentimentMetric as RuntimeSocialSentimentMetric,
)
from finance_plugin.providers.social_sentiment_snapshots import (
    SocialSentimentSourceBlock as RuntimeSocialSentimentSourceBlock,
)
from finance_plugin.schemas.market_data import MarketHistorySeriesRead, MarketQuoteRead
from plugin_runtime.common import CamelModel, ensure_timezone
from pydantic import Field, field_validator, model_validator

MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY = "signaldeck/finance/market_data_quote_lookup"
MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY = "signaldeck/finance/market_data_history_lookup"
MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY = "signaldeck/finance/market_data_ohlcv_lookup"
INDICATORS_LOOKUP_TOOL_KEY = "signaldeck/finance/indicators_lookup"
FUNDAMENTALS_LOOKUP_TOOL_KEY = "signaldeck/finance/fundamentals_lookup"
NEWS_LOOKUP_TOOL_KEY = "signaldeck/finance/news_lookup"
SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY = "signaldeck/finance/social_sentiment_lookup"
INSIDER_DATA_LOOKUP_TOOL_KEY = "signaldeck/finance/insider_data_lookup"
REPORT_LOOKUP_TOOL_KEY = "signaldeck/finance/reports_lookup"

NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS = (
    MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
    INDICATORS_LOOKUP_TOOL_KEY,
    FUNDAMENTALS_LOOKUP_TOOL_KEY,
    NEWS_LOOKUP_TOOL_KEY,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    INSIDER_DATA_LOOKUP_TOOL_KEY,
)

_NATIVE_TOOL_KEY_RE = re.compile(r"^signaldeck/finance/[a-z0-9_]+$")


def _validate_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_timezone(value)


class RuntimeNativeToolResult(CamelModel):
    tool_key: str = Field(min_length=1, max_length=200)

    @field_validator("tool_key")
    @classmethod
    def validate_tool_key(cls, value: str) -> str:
        normalized = value.strip().lower()
        if _NATIVE_TOOL_KEY_RE.fullmatch(normalized) is None:
            raise ValueError(
                "Native runtime tool keys must start with signaldeck. "
                + "and use lowercase dotted identifiers"
            )
        if normalized not in NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS:
            raise ValueError("Native runtime tool key is not registered as a financial tool result")
        return normalized


class RuntimeQuoteLookupResult(CamelModel):
    tool_key: Literal["signaldeck/finance/market_data_quote_lookup"] = (
        "signaldeck/finance/market_data_quote_lookup"
    )
    quotes: list[MarketQuoteRead]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeHistoryLookupResult(CamelModel):
    tool_key: Literal["signaldeck/finance/market_data_history_lookup"] = (
        "signaldeck/finance/market_data_history_lookup"
    )
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


class RuntimeOhlcvLookupResult(MarketDataOhlcvLookupResult):
    tool_key: Literal["signaldeck/finance/market_data_ohlcv_lookup"] = (
        "signaldeck/finance/market_data_ohlcv_lookup"
    )


class RuntimeIndicatorLookupResult(MarketDataIndicatorLookupResult):
    tool_key: Literal["signaldeck/finance/indicators_lookup"] = (
        "signaldeck/finance/indicators_lookup"
    )


class RuntimeFundamentalsLookupResult(MarketDataFundamentalsLookupResult):
    tool_key: Literal["signaldeck/finance/fundamentals_lookup"] = (
        "signaldeck/finance/fundamentals_lookup"
    )


class RuntimeNewsLookupResult(MarketDataNewsLookupResult):
    tool_key: Literal["signaldeck/finance/news_lookup"] = "signaldeck/finance/news_lookup"


class RuntimeSocialSentimentLookupResult(SocialSentimentLookupResult):
    tool_key: Literal["signaldeck/finance/social_sentiment_lookup"] = (
        "signaldeck/finance/social_sentiment_lookup"
    )


class RuntimeInsiderDataLookupResult(MarketDataInsiderDataLookupResult):
    tool_key: Literal["signaldeck/finance/insider_data_lookup"] = (
        "signaldeck/finance/insider_data_lookup"
    )


__all__ = [
    "FUNDAMENTALS_LOOKUP_TOOL_KEY",
    "INDICATORS_LOOKUP_TOOL_KEY",
    "INSIDER_DATA_LOOKUP_TOOL_KEY",
    "MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY",
    "MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY",
    "MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY",
    "NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS",
    "NEWS_LOOKUP_TOOL_KEY",
    "REPORT_LOOKUP_TOOL_KEY",
    "SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY",
    "RuntimeFinancialStatement",
    "RuntimeFinancialStatementLine",
    "RuntimeFundamentalMetric",
    "RuntimeFundamentalsLookupResult",
    "RuntimeHistoryLookupResult",
    "RuntimeIndicatorLookupResult",
    "RuntimeIndicatorRow",
    "RuntimeIndicatorValue",
    "RuntimeInsiderDataLookupResult",
    "RuntimeInsiderTransaction",
    "RuntimeNativeToolResult",
    "RuntimeNewsItem",
    "RuntimeNewsLookupResult",
    "RuntimeOhlcvLookupResult",
    "RuntimeOhlcvRow",
    "RuntimeOhlcvSeries",
    "RuntimeQuoteLookupResult",
    "RuntimeSocialSentimentLookupResult",
    "RuntimeSocialSentimentMetric",
    "RuntimeSocialSentimentSourceBlock",
]

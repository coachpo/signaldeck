"""Independent Finance providers, bounded inputs and safe degradation contracts."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import cast, get_type_hints

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "finance"):
    sys.path.insert(0, str(PLUGINS / directory))


from finance_plugin.contracts import (  # noqa: E402
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolSpec,
    RuntimeToolWarning,
)
from finance_plugin.ownership import FINANCE_WORKSPACE_EXTENSION_KEY  # noqa: E402
from finance_plugin.providers import news_provider  # noqa: E402
from finance_plugin.providers.news_provider import (  # noqa: E402
    AlphaVantageNewsProvider,
    DeterministicNewsProvider,
    NewsProvider,
    NewsProviderError,
    NewsProviderMalformedResponseError,
    NewsProviderMissingKeyError,
    NewsProviderRateLimitError,
    NewsProviderTimeoutError,
    NewsProviderUnavailableError,
    NewsProviderUnsupportedQueryError,
    NewsScope,
    NewsSentiment,
    ProviderNewsItem,
    ProviderNewsResult,
    YahooFinanceNewsProvider,
)
from finance_plugin.providers.quote_provider import (  # noqa: E402
    DeterministicQuoteProvider,
    ProviderFinancialStatement,
    ProviderFinancialStatementLine,
    ProviderFundamentalMetric,
    ProviderFundamentals,
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderInsiderTransaction,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
    QuoteProviderError,
    QuoteProviderMissingKeyError,
    QuoteProviderTimeoutError,
)
from finance_plugin.providers.social_sentiment_provider import (  # noqa: E402
    ProviderSocialSentimentMetric,
    ProviderSocialSentimentSourceBlock,
    ProviderSocialSentimentSourceResult,
    ProviderSocialSentimentWarning,
    RedditSocialSentimentAdapter,
    SocialSentimentProviderError,
    SocialSentimentProviderRateLimitError,
    SocialSentimentProviderTimeoutError,
    SocialSentimentSource,
    StockTwitsSocialSentimentAdapter,
    _RedditRequestConfig,
    _RedditTransport,
    _StockTwitsTransport,
)
from finance_plugin.providers.social_sentiment_service import SocialSentimentService  # noqa: E402
from finance_plugin.providers.social_sentiment_snapshots import (  # noqa: E402
    SocialSentimentLookupResult,
)
from finance_plugin.runtime_market_data import (  # noqa: E402
    FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
    FUNDAMENTALS_LOOKUP_TOOL_SPEC,
    INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
    INDICATORS_LOOKUP_TOOL_SPEC,
    INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
    INSIDER_DATA_LOOKUP_TOOL_SPEC,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
    MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
    NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
    NEWS_LOOKUP_TOOL_SPEC,
    SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    parse_fundamentals_lookup_arguments,
    parse_history_lookup_arguments,
    parse_indicators_lookup_arguments,
    parse_insider_data_lookup_arguments,
    parse_news_lookup_arguments,
    parse_ohlcv_lookup_arguments,
    parse_quote_lookup_arguments,
    parse_social_sentiment_lookup_arguments,
)
from finance_plugin.runtime_types import (  # noqa: E402
    FUNDAMENTALS_LOOKUP_TOOL_KEY,
    INDICATORS_LOOKUP_TOOL_KEY,
    INSIDER_DATA_LOOKUP_TOOL_KEY,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    NEWS_LOOKUP_TOOL_KEY,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    RuntimeIndicatorLookupResult,
    RuntimeIndicatorValue,
    RuntimeNewsItem,
    RuntimeNewsLookupResult,
    RuntimeOhlcvLookupResult,
    RuntimeOhlcvRow,
    RuntimeOhlcvSeries,
    RuntimeSocialSentimentLookupResult,
    RuntimeSocialSentimentMetric,
    RuntimeSocialSentimentSourceBlock,
)
from finance_plugin.services.market_data_service import (  # noqa: E402
    MarketDataService,
    MarketIndicatorSelection,
)

fake_FAKE_PROVIDER_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


class FakeFinanceProvider:

    def __init__(
        self,
        *,
        provider_name: str = "fake_runtime_provider",
        failing_symbols: set[str] | None = None,
        failure: QuoteProviderError | None = None,
        empty: bool = False,
        news_count: int = 0,
        insider_count: int = 0,
    ) -> None:
        self.provider_name = provider_name
        self.failing_symbols = failing_symbols or set()
        self.failure = failure
        self.empty = empty
        self.news_count = news_count
        self.insider_count = insider_count
        self.quote_calls: list[str] = []
        self.history_calls: list[tuple[str, str, str]] = []
        self.ohlcv_calls: list[tuple[str, datetime, datetime, str]] = []
        self.fundamental_calls: list[str] = []
        self.news_calls: list[
            tuple[list[str], str | None, str, datetime | None, datetime | None, int]
        ] = []
        self.insider_calls: list[tuple[str, datetime | None, datetime | None, int]] = []

    def fetch_symbol_name(self, symbol: str) -> str | None:
        return f"{symbol.upper()} Incorporated"

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        normalized_symbol = symbol.upper()
        self.quote_calls.append(normalized_symbol)
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"Quote unavailable for {normalized_symbol}")
        price = Decimal("120.25000000") if normalized_symbol == "NVDA" else Decimal("410.50000000")
        return ProviderQuote(
            symbol=normalized_symbol,
            name=f"{normalized_symbol} Incorporated",
            price=price,
            previous_close=price - Decimal("0.50000000"),
            currency="USD",
            provider=self.provider_name,
            as_of=fake_FAKE_PROVIDER_NOW,
        )

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        normalized_symbol = symbol.upper()
        self.history_calls.append((normalized_symbol, range_value, interval))
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"History unavailable for {normalized_symbol}")
        return ProviderHistorySeries(
            symbol=normalized_symbol,
            currency="USD",
            provider=self.provider_name,
            points=[
                ProviderHistoryPoint(at=datetime(2026, 1, 1, tzinfo=UTC), close=Decimal("118.75")),
                ProviderHistoryPoint(at=datetime(2026, 1, 2, tzinfo=UTC), close=Decimal("119.75")),
                ProviderHistoryPoint(at=fake_FAKE_PROVIDER_NOW, close=Decimal("120.25")),
            ],
        )

    def fetch_ohlcv(
        self, symbol: str, *, start_date: datetime, end_date: datetime, interval: str
    ) -> ProviderOhlcvSeries:
        normalized_symbol = symbol.upper()
        self.ohlcv_calls.append((normalized_symbol, start_date, end_date, interval))
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"OHLCV unavailable for {normalized_symbol}")
        mid_session = datetime(2026, 1, 2, 12, 0, tzinfo=timezone(timedelta(hours=-5)))
        return ProviderOhlcvSeries(
            symbol=normalized_symbol,
            currency="USD",
            provider=self.provider_name,
            rows=[
                ProviderOhlcvRow(
                    at=end_date + timedelta(days=1),
                    open=Decimal("999.00"),
                    high=Decimal("1000.00"),
                    low=Decimal("998.00"),
                    close=Decimal("999.50"),
                    volume=9999,
                ),
                ProviderOhlcvRow(
                    at=start_date,
                    open=Decimal("118.00"),
                    high=Decimal("121.00"),
                    low=Decimal("117.00"),
                    close=Decimal("119.75"),
                    volume=1000,
                    adjusted_close=Decimal("119.50"),
                ),
                ProviderOhlcvRow(
                    at=mid_session,
                    open=Decimal("119.00"),
                    high=Decimal("122.00"),
                    low=Decimal("118.00"),
                    close=Decimal("120.00"),
                    volume=1100,
                    adjusted_close=Decimal("119.80"),
                ),
                ProviderOhlcvRow(
                    at=start_date - timedelta(days=1),
                    open=Decimal("1.00"),
                    high=Decimal("2.00"),
                    low=Decimal("0.50"),
                    close=Decimal("1.50"),
                    volume=1,
                ),
                ProviderOhlcvRow(
                    at=end_date,
                    open=Decimal("119.75"),
                    high=Decimal("121.50"),
                    low=Decimal("119.00"),
                    close=Decimal("120.25"),
                    volume=1200,
                ),
            ],
        )

    def fetch_fundamentals(self, symbol: str) -> ProviderFundamentals:
        normalized_symbol = symbol.upper()
        self.fundamental_calls.append(normalized_symbol)
        if self.failure is not None:
            raise self.failure
        if self.empty:
            return ProviderFundamentals(
                symbol=normalized_symbol,
                provider=self.provider_name,
                as_of=datetime(2026, 1, 2, 12, tzinfo=timezone(timedelta(hours=-5))),
                metrics=[],
                statements=[],
            )
        return ProviderFundamentals(
            symbol=normalized_symbol,
            provider=self.provider_name,
            as_of=datetime(2026, 1, 2, 12, tzinfo=timezone(timedelta(hours=-5))),
            metrics=[
                ProviderFundamentalMetric(
                    name="market_cap",
                    value=Decimal("1000000.50"),
                    currency="USD",
                    period="ttm",
                    as_of=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                ),
                ProviderFundamentalMetric(
                    name="revenue_growth",
                    value=Decimal("0.18"),
                    period="ttm",
                    as_of=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                ),
                ProviderFundamentalMetric(
                    name="free_cash_flow_margin",
                    value=Decimal("0.19"),
                    period="ttm",
                    as_of=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                ),
            ],
            statements=[
                ProviderFinancialStatement(
                    statement_type="income_statement",
                    period="annual",
                    period_end=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                    lines=[
                        ProviderFinancialStatementLine(
                            name="revenue", value=Decimal("500000.25"), currency="USD"
                        )
                    ],
                ),
                ProviderFinancialStatement(
                    statement_type="balance_sheet",
                    period="quarterly",
                    period_end=datetime(2025, 10, 31, 21, tzinfo=timezone(timedelta(hours=-5))),
                    lines=[
                        ProviderFinancialStatementLine(
                            name="assets", value=Decimal("750000.00"), currency="USD"
                        )
                    ],
                ),
                ProviderFinancialStatement(
                    statement_type="cash_flow",
                    period="trailing_twelve_months",
                    period_end=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                    lines=[
                        ProviderFinancialStatementLine(
                            name="operating_cash_flow",
                            value=Decimal("125000.75"),
                            currency="USD",
                        )
                    ],
                ),
            ],
        )

    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: str,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        self.news_calls.append((symbols, query, scope, start_date, end_date, limit))
        if self.failure is not None:
            raise self.failure
        return ProviderNewsResult(
            provider=self.provider_name,
            items=[
                ProviderNewsItem(
                    title=f"News {index}",
                    source="wire",
                    published_at=datetime(2026, 1, 2, index, tzinfo=UTC),
                    symbols=symbols,
                    sentiment="neutral",
                )
                for index in range(self.news_count)
            ],
        )

    def fetch_insider_transactions(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderInsiderData:
        normalized_symbol = symbol.upper()
        self.insider_calls.append((normalized_symbol, start_date, end_date, limit))
        if self.failure is not None:
            raise self.failure
        return ProviderInsiderData(
            symbol=normalized_symbol,
            provider=self.provider_name,
            transactions=[
                ProviderInsiderTransaction(
                    insider_name=f"Insider {index}",
                    role="Director",
                    transaction_type="BUY",
                    shares=Decimal("10"),
                    price=Decimal("120.25"),
                    value=Decimal("1202.50"),
                    filed_at=datetime(2026, 1, 3, index, tzinfo=UTC),
                    transaction_date=datetime(2026, 1, 2, index, tzinfo=UTC),
                )
                for index in range(self.insider_count)
            ],
        )


alpha__FAKE_API_KEY = "".join(("alpha", "-", "test", "-", "key"))


class alpha__FakeAlphaClient:

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[dict[str, str | int]] = []

    def fetch_news(self, *, params: dict[str, str | int]) -> object:
        self.calls.append(dict(params))
        return self.payload


class alpha__TimeoutAlphaClient:

    def fetch_news(self, *, params: dict[str, str | int]) -> object:
        del params
        raise httpx.TimeoutException(f"timed out with apikey={alpha__FAKE_API_KEY}")


def alpha__payload(*, label: str = "Bullish") -> dict[str, object]:
    return {
        "feed": [
            {
                "title": "Nvidia expands AI platform",
                "source": "Alpha Wire",
                "url": "https://example.com/nvda-ai",
                "summary": "Chipmaker updates its AI stack.",
                "time_published": "20250508T143000",
                "overall_sentiment_label": label,
                "ticker_sentiment": [
                    {"ticker": "NVDA", "ticker_sentiment_label": "Bullish"},
                    {"ticker": " MSFT "},
                    {"ticker": ""},
                ],
            }
        ]
    }


def test_alpha_news_provider_parses_symbol_feed_and_params() -> None:
    client = alpha__FakeAlphaClient(alpha__payload())
    provider = AlphaVantageNewsProvider(api_key=alpha__FAKE_API_KEY, client=client, timeout=2.5)
    result = provider.fetch_news(
        symbols=[" nvda ", "MSFT", "nvda"],
        query=None,
        scope="symbol",
        start_date=datetime(2025, 5, 1, tzinfo=UTC),
        end_date=datetime(2025, 5, 9, 12, 30, tzinfo=UTC),
        limit=5,
    )
    assert result.provider == "alpha_vantage"
    assert client.calls == [
        {
            "function": "NEWS_SENTIMENT",
            "source": "signaldeck",
            "apikey": alpha__FAKE_API_KEY,
            "limit": 5,
            "tickers": "NVDA,MSFT",
            "time_from": "20250501T0000",
            "time_to": "20250509T1230",
        }
    ]
    assert len(result.items) == 1
    assert result.items[0].title == "Nvidia expands AI platform"
    assert result.items[0].source == "Alpha Wire"
    assert result.items[0].url == "https://example.com/nvda-ai"
    assert result.items[0].summary == "Chipmaker updates its AI stack."
    assert result.items[0].published_at == datetime(2025, 5, 8, 14, 30, tzinfo=UTC)
    assert result.items[0].symbols == ["NVDA", "MSFT"]
    assert result.items[0].sentiment == "positive"


def test_alpha_global_and_market_scopes_use_default_topics_without_symbols() -> None:
    client = alpha__FakeAlphaClient(alpha__payload(label="Neutral"))
    provider = AlphaVantageNewsProvider(api_key=alpha__FAKE_API_KEY, client=client)
    provider.fetch_news(
        symbols=[], query=None, scope="global", start_date=None, end_date=None, limit=3
    )
    provider.fetch_news(
        symbols=[], query=None, scope="market", start_date=None, end_date=None, limit=4
    )
    provider.fetch_news(
        symbols=["aapl"],
        query=None,
        scope="market",
        start_date=None,
        end_date=None,
        limit=5,
    )
    assert client.calls == [
        {
            "function": "NEWS_SENTIMENT",
            "source": "signaldeck",
            "apikey": alpha__FAKE_API_KEY,
            "limit": 3,
            "topics": "financial_markets,economy_macro,economy_monetary",
        },
        {
            "function": "NEWS_SENTIMENT",
            "source": "signaldeck",
            "apikey": alpha__FAKE_API_KEY,
            "limit": 4,
            "topics": "financial_markets,economy_macro,economy_monetary",
        },
        {
            "function": "NEWS_SENTIMENT",
            "source": "signaldeck",
            "apikey": alpha__FAKE_API_KEY,
            "limit": 5,
            "tickers": "AAPL",
        },
    ]


@pytest.mark.parametrize(
    ("provider_label", "expected"),
    [
        ("Positive", "positive"),
        ("Somewhat-Bullish", "positive"),
        ("Negative", "negative"),
        ("Bearish", "negative"),
        ("Neutral", "neutral"),
        ("Mixed", "mixed"),
        ("Unclear", "mixed"),
    ],
)
def test_alpha_sentiment_labels_map_to_provider_sentiment(
    provider_label: str, expected: str
) -> None:
    provider = AlphaVantageNewsProvider(
        api_key=alpha__FAKE_API_KEY,
        client=alpha__FakeAlphaClient(alpha__payload(label=provider_label)),
    )
    result = provider.fetch_news(
        symbols=["nvda"],
        query=None,
        scope="symbol",
        start_date=None,
        end_date=None,
        limit=1,
    )
    assert result.items[0].sentiment == expected


def test_alpha_unsupported_query_without_symbols_raises_degradable_error() -> None:
    client = alpha__FakeAlphaClient(alpha__payload())
    provider = AlphaVantageNewsProvider(api_key=alpha__FAKE_API_KEY, client=client)
    with pytest.raises(NewsProviderUnsupportedQueryError) as exc_info:
        provider.fetch_news(
            symbols=[],
            query="Federal Reserve meeting",
            scope="market",
            start_date=None,
            end_date=None,
            limit=5,
        )
    assert exc_info.value.code == "provider_unsupported_query"
    assert client.calls == []


def test_alpha_missing_key_raises_without_secret_name() -> None:
    provider = AlphaVantageNewsProvider(
        api_key=None, client=alpha__FakeAlphaClient(alpha__payload())
    )
    with pytest.raises(NewsProviderMissingKeyError) as exc_info:
        provider.fetch_news(
            symbols=["nvda"],
            query=None,
            scope="symbol",
            start_date=None,
            end_date=None,
            limit=5,
        )
    assert "apiKey" not in str(exc_info.value)
    assert exc_info.value.details == {"provider": "alpha_vantage"}


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        (
            {"Note": f"Thank you for using Alpha Vantage. api_key={alpha__FAKE_API_KEY}"},
            NewsProviderRateLimitError,
        ),
        (
            {"Information": f"Invalid API key. {alpha__FAKE_API_KEY}"},
            NewsProviderMissingKeyError,
        ),
        ({"feed": "not-a-list"}, NewsProviderMalformedResponseError),
        ([{"feed": []}], NewsProviderMalformedResponseError),
    ],
)
def test_alpha_failure_payloads_raise_structured_redacted_errors(
    payload: object, error_type: type[Exception]
) -> None:
    provider = AlphaVantageNewsProvider(
        api_key=alpha__FAKE_API_KEY, client=alpha__FakeAlphaClient(payload)
    )
    with pytest.raises(error_type) as exc_info:
        provider.fetch_news(
            symbols=["nvda"],
            query=None,
            scope="symbol",
            start_date=None,
            end_date=None,
            limit=5,
        )
    assert alpha__FAKE_API_KEY not in str(exc_info.value)


def test_alpha_timeout_raises_redacted_timeout_error() -> None:
    provider = AlphaVantageNewsProvider(
        api_key=alpha__FAKE_API_KEY, client=alpha__TimeoutAlphaClient()
    )
    with pytest.raises(NewsProviderTimeoutError) as exc_info:
        provider.fetch_news(
            symbols=["nvda"],
            query=None,
            scope="symbol",
            start_date=None,
            end_date=None,
            limit=5,
        )
    assert exc_info.value.code == "provider_timeout"
    assert alpha__FAKE_API_KEY not in str(exc_info.value)


class yahoo__FakeYahooSearchClient:

    def __init__(self, payloads: dict[str, list[dict[str, object]]]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, int]] = []

    def search_news(self, *, query: str, limit: int) -> list[dict[str, object]]:
        self.calls.append((query, limit))
        return self.payloads.get(query, [])


class yahoo__MalformedYahooSearchClient:

    def search_news(self, *, query: str, limit: int) -> list[dict[str, object]]:
        del query, limit
        raise NewsProviderMalformedResponseError("Yahoo Finance news payload was malformed")


def yahoo__epoch(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp())


def test_yahoo_news_provider_parses_nested_content_articles() -> None:
    client = yahoo__FakeYahooSearchClient(
        {
            "NVDA": [
                {
                    "content": {
                        "title": "Nvidia expands AI platform",
                        "summary": "Chipmaker updates its AI stack.",
                        "provider": {"displayName": "Yahoo Finance"},
                        "canonicalUrl": {"url": "https://finance.yahoo.com/nvda-ai"},
                        "pubDate": "2025-05-08T14:30:00Z",
                    }
                }
            ]
        }
    )
    provider = YahooFinanceNewsProvider(search_client=client)
    result = provider.fetch_news(
        symbols=["nvda"],
        query=None,
        scope="symbol",
        start_date=datetime(2025, 5, 1, tzinfo=UTC),
        end_date=datetime(2025, 5, 9, tzinfo=UTC),
        limit=5,
    )
    assert result.provider == "yahoo"
    assert client.calls == [("NVDA", 5)]
    assert len(result.items) == 1
    assert result.items[0].title == "Nvidia expands AI platform"
    assert result.items[0].summary == "Chipmaker updates its AI stack."
    assert result.items[0].source == "Yahoo Finance"
    assert result.items[0].url == "https://finance.yahoo.com/nvda-ai"
    assert result.items[0].published_at == datetime(2025, 5, 8, 14, 30, tzinfo=UTC)
    assert result.items[0].symbols == ["NVDA"]


def test_yahoo_news_provider_parses_flat_provider_publish_time_articles() -> None:
    client = yahoo__FakeYahooSearchClient(
        {
            "NVDA": [
                {
                    "title": "Nvidia flat article",
                    "summary": "Flat payload summary.",
                    "publisher": "Reuters",
                    "link": "https://example.com/nvda-flat",
                    "providerPublishTime": yahoo__epoch(2025, 5, 6),
                }
            ]
        }
    )
    provider = YahooFinanceNewsProvider(search_client=client)
    result = provider.fetch_news(
        symbols=["nvda"],
        query=None,
        scope="symbol",
        start_date=datetime(2025, 5, 1, tzinfo=UTC),
        end_date=datetime(2025, 5, 9, tzinfo=UTC),
        limit=5,
    )
    assert len(result.items) == 1
    assert result.items[0].title == "Nvidia flat article"
    assert result.items[0].source == "Reuters"
    assert result.items[0].url == "https://example.com/nvda-flat"
    assert result.items[0].published_at == datetime(2025, 5, 6, tzinfo=UTC)


def test_yahoo_global_news_defaults_dedupe_by_url_then_normalized_title() -> None:
    client = yahoo__FakeYahooSearchClient(
        {
            "markets": [
                {
                    "title": "Markets rally",
                    "publisher": "Wire",
                    "link": "https://example.com/markets-rally",
                    "providerPublishTime": yahoo__epoch(2025, 5, 7),
                },
                {
                    "title": "Different title",
                    "publisher": "Wire",
                    "link": "https://example.com/markets-rally",
                    "providerPublishTime": yahoo__epoch(2025, 5, 7),
                },
            ],
            "macro": [
                {
                    "title": "  markets   rally ",
                    "publisher": "Wire",
                    "link": "https://example.com/duplicate-title",
                    "providerPublishTime": yahoo__epoch(2025, 5, 6),
                },
                {
                    "title": "Central bank holds rates",
                    "publisher": "Wire",
                    "link": "https://example.com/rates",
                    "providerPublishTime": yahoo__epoch(2025, 5, 6),
                },
            ],
        }
    )
    provider = YahooFinanceNewsProvider(
        search_client=client,
        global_queries=("markets", "macro"),
        global_lookback_days=7,
    )
    result = provider.fetch_news(
        symbols=[],
        query=None,
        scope="global",
        start_date=None,
        end_date=datetime(2025, 5, 9, tzinfo=UTC),
        limit=10,
    )
    assert client.calls == [("markets", 10), ("macro", 10)]
    assert [item.title for item in result.items] == [
        "Markets rally",
        "Central bank holds rates",
    ]


def test_yahoo_news_provider_excludes_future_and_undated_historical_articles() -> None:
    client = yahoo__FakeYahooSearchClient(
        {
            "NVDA": [
                {
                    "title": "Future event",
                    "publisher": "Wire",
                    "link": "https://example.com/future",
                    "providerPublishTime": yahoo__epoch(2025, 6, 1),
                },
                {
                    "title": "Undated historical leak",
                    "publisher": "Wire",
                    "link": "https://example.com/undated",
                },
                {
                    "title": "Past event",
                    "publisher": "Wire",
                    "link": "https://example.com/past",
                    "providerPublishTime": yahoo__epoch(2025, 5, 5),
                },
            ]
        }
    )
    provider = YahooFinanceNewsProvider(search_client=client)
    result = provider.fetch_news(
        symbols=["nvda"],
        query=None,
        scope="symbol",
        start_date=datetime(2025, 5, 1, tzinfo=UTC),
        end_date=datetime(2025, 5, 9, tzinfo=UTC),
        limit=10,
    )
    assert [item.title for item in result.items] == ["Past event"]


def test_yahoo_news_provider_keeps_undated_article_when_window_reaches_today() -> None:
    client = yahoo__FakeYahooSearchClient(
        {
            "NVDA": [
                {
                    "title": "Live undated article",
                    "publisher": "Wire",
                    "link": "https://example.com/live-undated",
                }
            ]
        }
    )
    provider = YahooFinanceNewsProvider(search_client=client)
    today = datetime.now(UTC)
    result = provider.fetch_news(
        symbols=["nvda"],
        query=None,
        scope="symbol",
        start_date=today - timedelta(days=1),
        end_date=today,
        limit=10,
    )
    assert [item.title for item in result.items] == ["Live undated article"]
    assert result.items[0].published_at == today


def test_yahoo_news_provider_malformed_payload_uses_typed_error() -> None:
    provider = YahooFinanceNewsProvider(search_client=yahoo__MalformedYahooSearchClient())
    with pytest.raises(NewsProviderMalformedResponseError, match="Yahoo Finance news payload"):
        provider.fetch_news(
            symbols=["nvda"],
            query=None,
            scope="symbol",
            start_date=datetime(2025, 5, 1, tzinfo=UTC),
            end_date=datetime(2025, 5, 9, tzinfo=UTC),
            limit=5,
        )


def test_deterministic_news_provider_preserves_existing_shape() -> None:
    provider = DeterministicNewsProvider()
    result = provider.fetch_news(
        symbols=[" nvda ", "NVDA"],
        query=" earnings ",
        scope="symbol",
        start_date=datetime(2024, 3, 1, tzinfo=UTC),
        end_date=datetime(2024, 4, 1, tzinfo=UTC),
        limit=5,
    )
    assert result.provider == "deterministic_test"
    assert len(result.items) == 1
    assert result.items[0].title == "NVDA deterministic market update"
    assert result.items[0].source == "deterministic_test"
    assert result.items[0].published_at == datetime(2024, 3, 29, tzinfo=UTC)
    assert result.items[0].symbols == ["NVDA"]
    assert result.items[0].sentiment == "neutral"


def test_news_provider_contract_exports_sentiment_alias_and_error_codes() -> None:
    unavailable = NewsProviderUnavailableError(
        "provider unavailable", details={"provider": "news_test"}
    )
    malformed = NewsProviderMalformedResponseError(
        "provider malformed response", details={"provider": "news_test"}
    )
    assert get_type_hints(ProviderNewsItem)["sentiment"] == NewsSentiment | None
    assert unavailable.code == "provider_unavailable"
    assert unavailable.details == {"provider": "news_test"}
    assert malformed.code == "provider_malformed_response"
    assert malformed.details == {"provider": "news_test"}
    assert NewsProviderUnsupportedQueryError("unsupported").code == "provider_unsupported_query"
    assert "NewsSentiment" in news_provider.__all__
    assert "NewsProviderUnavailableError" in news_provider.__all__
    assert "NewsProviderMalformedResponseError" in news_provider.__all__
    assert "NewsProviderUnsupportedQueryError" in news_provider.__all__


def market__news_provider(provider: object) -> NewsProvider:
    return cast(NewsProvider, provider)


def market__service(provider: object) -> MarketDataService:
    return MarketDataService(
        session=cast(Session, None),
        quote_provider=DeterministicQuoteProvider(),
        news_providers=(market__news_provider(provider),),
    )


class market__NewsProvider:

    def __init__(
        self,
        *,
        provider_name: str = "news_test",
        items: list[ProviderNewsItem] | None = None,
        failure: NewsProviderError | None = None,
    ) -> None:
        self.provider_name: str = provider_name
        self.items: list[ProviderNewsItem] = list(items or [])
        self.failure: NewsProviderError | None = failure
        self.news_calls: list[
            tuple[list[str], str | None, str, datetime | None, datetime | None, int]
        ] = []

    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: NewsScope,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        self.news_calls.append((symbols, query, scope, start_date, end_date, limit))
        if self.failure is not None:
            raise self.failure
        return ProviderNewsResult(provider=self.provider_name, items=self.items[:limit])


@pytest.fixture()
def market_news_service_factory() -> Callable[[object], MarketDataService]:
    return market__service


def test_news_adapter_rate_limit_degrades_with_structured_warning(
    market_news_service_factory: Callable[[object], MarketDataService],
) -> None:
    provider = market__NewsProvider(
        failure=NewsProviderRateLimitError(
            "provider rate limited api_key=sk-secret",
            details={"status": "429", "api_key": "sk-secret"},
        )
    )
    service = market_news_service_factory(provider)
    result = service.get_news_snapshot(
        symbols=["nvda"], providers=[market__news_provider(provider)]
    )
    payload = result.model_dump(mode="json", by_alias=True)
    assert payload["items"] == []
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_provider_rate_limited",
        "news_unavailable",
    ]
    warning_json = json.dumps(payload["warnings"])
    assert "sk-secret" not in warning_json
    assert "apiKey" not in warning_json


def test_news_adapter_timeout_degrades_with_structured_warning(
    market_news_service_factory: Callable[[object], MarketDataService],
) -> None:
    provider = market__NewsProvider(failure=NewsProviderTimeoutError("news provider timed out"))
    service = market_news_service_factory(provider)
    result = service.get_news_snapshot(
        symbols=["nvda"], providers=[market__news_provider(provider)]
    )
    payload = result.model_dump(mode="json", by_alias=True)
    assert payload["items"] == []
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_provider_timeout",
        "news_unavailable",
    ]


def test_news_adapter_unsupported_query_falls_back_with_structured_warning(
    market_news_service_factory: Callable[[object], MarketDataService],
) -> None:
    primary_provider = market__NewsProvider(
        provider_name="alpha_vantage",
        failure=NewsProviderUnsupportedQueryError(
            "Alpha Vantage free-text news queries require symbols",
            details={"provider": "alpha_vantage"},
        ),
    )
    fallback_provider = market__NewsProvider(
        provider_name="fallback_news",
        items=[
            ProviderNewsItem(
                title="Fallback market item",
                source="wire",
                published_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
        ],
    )
    service = market_news_service_factory(primary_provider)
    result = service.get_news_snapshot(
        query="Fed meeting",
        providers=[
            market__news_provider(primary_provider),
            market__news_provider(fallback_provider),
        ],
    )
    payload = result.model_dump(mode="json", by_alias=True)
    assert [item["title"] for item in cast(list[dict[str, object]], payload["items"])] == [
        "Fallback market item"
    ]
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_provider_unsupported_query"
    ]


def test_news_adapter_empty_result_returns_structured_warning(
    market_news_service_factory: Callable[[object], MarketDataService],
) -> None:
    provider = market__NewsProvider()
    service = market_news_service_factory(provider)
    result = service.get_news_snapshot(
        symbols=["nvda"], providers=[market__news_provider(provider)]
    )
    payload = result.model_dump(mode="json", by_alias=True)
    assert payload["items"] == []
    assert payload["warnings"] == [
        {
            "code": "news_empty",
            "message": "No news returned for the request",
            "details": [
                {"key": "provider", "value": "news_test"},
                {"key": "query", "value": ""},
                {"key": "scope", "value": "symbol"},
                {"key": "symbols", "value": "NVDA"},
            ],
        }
    ]


def test_news_adapter_empty_after_filter_preserves_empty_warning(
    market_news_service_factory: Callable[[object], MarketDataService],
) -> None:
    provider = market__NewsProvider(
        items=[
            ProviderNewsItem(
                title="Future item",
                source="wire",
                published_at=datetime(2025, 6, 1, tzinfo=UTC),
                symbols=["NVDA"],
            )
        ]
    )
    service = market_news_service_factory(provider)
    result = service.get_news_snapshot(
        symbols=["nvda"],
        start_date=datetime(2025, 5, 1, tzinfo=UTC),
        end_date=datetime(2025, 5, 9, tzinfo=UTC),
        providers=[market__news_provider(provider)],
    )
    payload = result.model_dump(mode="json", by_alias=True)
    assert payload["items"] == []
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_empty"
    ]


def test_news_adapter_global_warning_and_truncation_preserved(
    market_news_service_factory: Callable[[object], MarketDataService],
) -> None:
    provider = market__NewsProvider(
        items=[
            ProviderNewsItem(
                title=f"Global item {index}",
                source="wire",
                published_at=datetime(2025, 5, index + 1, tzinfo=UTC),
            )
            for index in range(3)
        ]
    )
    service = market_news_service_factory(provider)
    result = service.get_news_snapshot(
        scope="global",
        end_date=datetime(2025, 5, 9, tzinfo=UTC),
        item_limit=2,
        providers=[market__news_provider(provider)],
    )
    payload = result.model_dump(mode="json", by_alias=True)
    assert [item["title"] for item in cast(list[dict[str, object]], payload["items"])] == [
        "Global item 2",
        "Global item 1",
    ]
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_truncated",
        "news_global_coverage_limited",
    ]


def test_news_adapter_partial_result_falls_back_after_provider_outage(
    market_news_service_factory: Callable[[object], MarketDataService],
) -> None:
    first_provider = market__NewsProvider(
        provider_name="primary_news",
        failure=NewsProviderError("primary outage", code="provider_unavailable"),
    )
    second_provider = market__NewsProvider(
        provider_name="secondary_news",
        items=[
            ProviderNewsItem(
                title="Fallback item",
                source="wire",
                published_at=datetime(2026, 1, 2, tzinfo=UTC),
                symbols=["NVDA"],
            )
        ],
    )
    service = market_news_service_factory(first_provider)
    result = service.get_news_snapshot(
        symbols=["nvda"],
        providers=[
            market__news_provider(first_provider),
            market__news_provider(second_provider),
        ],
    )
    payload = result.model_dump(mode="json", by_alias=True)
    assert [item["title"] for item in cast(list[dict[str, object]], payload["items"])] == [
        "Fallback item"
    ]
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_provider_unavailable"
    ]


class social__SocialAdapter:

    def __init__(
        self,
        *,
        source: SocialSentimentSource,
        provider_name: str,
        blocks: list[ProviderSocialSentimentSourceBlock] | None = None,
        metrics: list[ProviderSocialSentimentMetric] | None = None,
        warnings: list[ProviderSocialSentimentWarning] | None = None,
        failure: SocialSentimentProviderError | None = None,
    ) -> None:
        self.source: SocialSentimentSource = source
        self.provider_name: str = provider_name
        self.blocks: list[ProviderSocialSentimentSourceBlock] = list(blocks or [])
        self.metrics: list[ProviderSocialSentimentMetric] = list(metrics or [])
        self.warnings: list[ProviderSocialSentimentWarning] = list(warnings or [])
        self.failure: SocialSentimentProviderError | None = failure
        self.calls: list[tuple[str, datetime | None, datetime | None, int]] = []

    def fetch_source_blocks(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderSocialSentimentSourceResult:
        self.calls.append((symbol, start_date, end_date, limit))
        if self.failure is not None:
            raise self.failure
        return ProviderSocialSentimentSourceResult(
            source=self.source,
            provider=self.provider_name,
            source_blocks=self.blocks[:limit],
            metrics=self.metrics,
            warnings=self.warnings,
        )


class social__FakeJsonFetcher:

    def __init__(self, payloads: list[dict[str, object]] | None = None) -> None:
        self.payloads: list[dict[str, object]] = list(payloads or [])
        self.calls: list[tuple[str, dict[str, str | int]]] = []
        self.failures: list[SocialSentimentProviderError] = []

    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str | int],
        timeout: float,
        provider: str,
        source: SocialSentimentSource,
    ) -> dict[str, object]:
        self.calls.append((url, params))
        if self.failures:
            raise self.failures.pop(0)
        return self.payloads.pop(0)


class social__FakeTextFetcher:

    def __init__(self, payloads: list[str] | None = None) -> None:
        self.payloads: list[str] = list(payloads or [])
        self.calls: list[tuple[str, dict[str, str | int]]] = []
        self.failures: list[SocialSentimentProviderError] = []

    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str | int],
        timeout: float,
        provider: str,
        source: SocialSentimentSource,
    ) -> str:
        self.calls.append((url, params))
        if self.failures:
            raise self.failures.pop(0)
        return self.payloads.pop(0)


class social__SleepRecorder:

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, delay_seconds: float) -> None:
        self.calls.append(delay_seconds)


def social__reddit_config(
    *, subreddits: tuple[str, ...] = ("stocks",), retry_after_max_seconds: float = 2.0
) -> _RedditRequestConfig:
    return _RedditRequestConfig(
        subreddits=subreddits, retry_after_max_seconds=retry_after_max_seconds
    )


def social__payload(
    result: RuntimeSocialSentimentLookupResult | SocialSentimentLookupResult,
) -> dict[str, object]:
    return cast(dict[str, object], result.model_dump(mode="json", by_alias=True))


def social__reddit_rss_fixture() -> str:
    return (
        '\n    <rss version="2.0">\n      <channel>\n        <item>\n         '
        " <title>NVDA retail thread</title>\n          <description>Discuss"
        "ion volume increased.</description>\n          <link>https://www.r"
        "eddit.com/r/stocks/comments/1/nvda</link>\n          <pubDate>Fri,"
        " 02 Jan 2026 10:00:00 GMT</pubDate>\n        </item>\n      </chann"
        "el>\n    </rss>\n    "
    )


def social__reddit_atom_fixture() -> str:
    return (
        '\n    <feed xmlns="http://www.w3.org/2005/Atom">\n      <entry>\n   '
        '     <title>NVDA Atom thread</title>\n        <content type="html"'
        ">\n          &lt;div&gt;&lt;p&gt;Retail &lt;b&gt;interest&lt;/b&gt"
        "; rose for NVDA.&lt;/p&gt;\n          &lt;/div&gt;\n        </conte"
        'nt>\n        <link href="https://www.reddit.com/r/stocks/comments/'
        '3/nvda_atom/" />\n        <published>2026-01-02T10:30:00+00:00</pu'
        "blished>\n      </entry>\n    </feed>\n    "
    )


def social__reddit_empty_atom_fixture() -> str:
    return '<feed xmlns="http://www.w3.org/2005/Atom"><title>empty</title></feed>'


def social__reddit_json_fixture() -> dict[str, object]:
    return {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "NVDA JSON thread",
                        "selftext": "JSON fallback discussion.",
                        "permalink": "/r/stocks/comments/2/nvda_json/",
                        "created_utc": 1767351600,
                        "score": 42,
                        "num_comments": 7,
                    }
                }
            ]
        }
    }


def social__stocktwits_json_fixture() -> dict[str, object]:
    return {
        "messages": [
            {
                "id": 123,
                "body": "Bullish into earnings.",
                "created_at": "2026-01-02T12:00:00Z",
                "user": {"username": "trader"},
                "entities": {"sentiment": {"basic": "Bullish"}},
            }
        ]
    }


def social__stocktwits_message(
    *, message_id: int, body: str, created_at: str, sentiment: str | None
) -> dict[str, object]:
    entities: dict[str, object] = {}
    if sentiment is not None:
        entities = {"sentiment": {"basic": sentiment}}
    return {
        "id": message_id,
        "body": body,
        "created_at": created_at,
        "user": {"username": "trader"},
        "entities": entities,
    }


def test_reddit_adapter_parses_rss_items_before_json_fetch() -> None:
    text_fetcher = social__FakeTextFetcher([social__reddit_rss_fixture()])
    json_fetcher = social__FakeJsonFetcher([social__reddit_json_fixture()])
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=social__reddit_config(),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=social__SleepRecorder(),
        ),
    )
    result = adapter.fetch_source_blocks(
        " nvda ",
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 1, 3, tzinfo=UTC),
        limit=5,
    )
    assert json_fetcher.calls == []
    assert len(text_fetcher.calls) == 1
    assert text_fetcher.calls[0][0].endswith("/r/stocks/search.rss")
    assert result.warnings == []
    assert result.metrics == []
    block = result.source_blocks[0]
    assert block.title == "NVDA retail thread"
    assert block.summary == "Discussion volume increased."
    assert block.url == "https://www.reddit.com/r/stocks/comments/1/nvda"
    assert block.as_of == datetime(2026, 1, 2, 10, tzinfo=UTC)
    assert block.symbols == ["NVDA"]
    assert block.metrics == []


def test_reddit_adapter_uses_rss_default_params_and_parses_atom_without_fake_metrics() -> None:
    text_fetcher = social__FakeTextFetcher([social__reddit_atom_fixture()])
    json_fetcher = social__FakeJsonFetcher([social__reddit_json_fixture()])
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=social__reddit_config(),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=social__SleepRecorder(),
        ),
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert json_fetcher.calls == []
    assert text_fetcher.calls == [
        (
            "https://www.reddit.com/r/stocks/search.rss",
            {"q": "NVDA", "restrict_sr": "on", "sort": "new", "t": "week", "limit": 5},
        )
    ]
    assert result.metrics == []
    block = result.source_blocks[0]
    assert block.title == "NVDA Atom thread"
    assert block.summary == "Retail interest rose for NVDA."
    assert block.url == "https://www.reddit.com/r/stocks/comments/3/nvda_atom/"
    assert block.as_of == datetime(2026, 1, 2, 10, 30, tzinfo=UTC)
    assert block.metrics == []


def test_reddit_adapter_retries_rss_429_once_with_injected_backoff() -> None:
    text_fetcher = social__FakeTextFetcher([social__reddit_rss_fixture()])
    text_fetcher.failures.append(SocialSentimentProviderRateLimitError("reddit rss rate limited"))
    sleep = social__SleepRecorder()
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=social__reddit_config(),
        transport=_RedditTransport(
            json_fetcher=social__FakeJsonFetcher(),
            text_fetcher=text_fetcher,
            sleep=sleep,
        ),
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert len(text_fetcher.calls) == 2
    assert sleep.calls == [1.0]
    assert result.warnings == []
    assert [block.title for block in result.source_blocks] == ["NVDA retail thread"]


def test_reddit_adapter_caps_retry_after_and_warns_when_rss_stays_rate_limited() -> None:
    text_fetcher = social__FakeTextFetcher()
    text_fetcher.failures.extend(
        [
            SocialSentimentProviderRateLimitError(
                "reddit rss rate limited",
                details={"status": "429", "retryAfterSeconds": "30"},
            ),
            SocialSentimentProviderRateLimitError(
                "reddit rss still rate limited",
                details={"status": "429", "retryAfterSeconds": "30"},
            ),
        ]
    )
    sleep = social__SleepRecorder()
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=social__reddit_config(retry_after_max_seconds=2.0),
        transport=_RedditTransport(
            json_fetcher=social__FakeJsonFetcher([social__reddit_json_fixture()]),
            text_fetcher=text_fetcher,
            sleep=sleep,
        ),
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert len(text_fetcher.calls) == 2
    assert sleep.calls == [2.0]
    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_rate_limited"]
    assert result.warnings[0].details == {
        "provider": "reddit_public_search",
        "source": "reddit",
        "status": "429",
        "retryAfterSeconds": "30",
        "subreddit": "stocks",
    }


def test_reddit_adapter_falls_back_to_json_when_rss_is_unavailable() -> None:
    text_fetcher = social__FakeTextFetcher()
    text_fetcher.failures.append(
        SocialSentimentProviderError("reddit rss unavailable", code="provider_unavailable")
    )
    json_fetcher = social__FakeJsonFetcher([social__reddit_json_fixture()])
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=social__reddit_config(),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=social__SleepRecorder(),
        ),
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert len(text_fetcher.calls) == 1
    assert len(json_fetcher.calls) == 1
    assert result.warnings == []
    assert result.metrics[0].name == "mention_count"
    assert result.source_blocks[0].title == "NVDA JSON thread"
    assert result.source_blocks[0].metrics[0].name == "score"


def test_reddit_adapter_falls_back_to_json_when_rss_is_malformed() -> None:
    text_fetcher = social__FakeTextFetcher(["<feed>"])
    json_fetcher = social__FakeJsonFetcher([social__reddit_json_fixture()])
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=social__reddit_config(),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=social__SleepRecorder(),
        ),
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert len(text_fetcher.calls) == 1
    assert len(json_fetcher.calls) == 1
    assert result.source_blocks[0].title == "NVDA JSON thread"
    assert result.source_blocks[0].metrics[0].name == "score"
    assert result.warnings == []


def test_reddit_adapter_falls_back_to_json_when_rss_is_empty() -> None:
    text_fetcher = social__FakeTextFetcher([social__reddit_empty_atom_fixture()])
    json_fetcher = social__FakeJsonFetcher([social__reddit_json_fixture()])
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=social__reddit_config(),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=social__SleepRecorder(),
        ),
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert len(text_fetcher.calls) == 1
    assert len(json_fetcher.calls) == 1
    assert result.source_blocks[0].title == "NVDA JSON thread"
    assert result.metrics[0].name == "mention_count"


def test_reddit_adapter_preserves_useful_rss_when_later_json_fallback_fails() -> None:
    text_fetcher = social__FakeTextFetcher(
        [social__reddit_atom_fixture(), social__reddit_empty_atom_fixture()]
    )
    json_fetcher = social__FakeJsonFetcher()
    json_fetcher.failures.append(SocialSentimentProviderTimeoutError("reddit json timed out"))
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=social__reddit_config(subreddits=("stocks", "investing")),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=social__SleepRecorder(),
        ),
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=10)
    assert [block.title for block in result.source_blocks] == ["NVDA Atom thread"]
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_timeout"]
    assert result.warnings[0].details["subreddit"] == "investing"


def test_stocktwits_adapter_returns_warning_instead_of_raising_on_failure() -> None:
    json_fetcher = social__FakeJsonFetcher([social__stocktwits_json_fixture()])
    json_fetcher.failures.append(
        SocialSentimentProviderRateLimitError("stocktwits rate limited", details={"status": "429"})
    )
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1, transport=_StockTwitsTransport(json_fetcher=json_fetcher)
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_rate_limited"]
    assert result.warnings[0].details == {
        "provider": "stocktwits_public_stream",
        "source": "stocktwits",
        "status": "429",
    }


def test_stocktwits_adapter_returns_warning_for_timeout_failure() -> None:
    json_fetcher = social__FakeJsonFetcher()
    json_fetcher.failures.append(SocialSentimentProviderTimeoutError("stocktwits timed out"))
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1, transport=_StockTwitsTransport(json_fetcher=json_fetcher)
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_timeout"]


def test_stocktwits_adapter_returns_warning_for_provider_unavailable_failure() -> None:
    json_fetcher = social__FakeJsonFetcher()
    json_fetcher.failures.append(
        SocialSentimentProviderError(
            "stocktwits outage", code="provider_unavailable", details={"status": "503"}
        )
    )
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1, transport=_StockTwitsTransport(json_fetcher=json_fetcher)
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_unavailable"]
    assert result.warnings[0].details["status"] == "503"


def test_stocktwits_adapter_returns_warning_for_malformed_json_failure() -> None:
    json_fetcher = social__FakeJsonFetcher()
    json_fetcher.failures.append(
        SocialSentimentProviderError(
            "stocktwits returned malformed json", details={"payload": "json"}
        )
    )
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1, transport=_StockTwitsTransport(json_fetcher=json_fetcher)
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_error"]
    assert result.warnings[0].details["payload"] == "json"


def test_stocktwits_adapter_warns_when_messages_payload_is_missing() -> None:
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(json_fetcher=social__FakeJsonFetcher([{}])),
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_malformed_payload"]
    assert result.warnings[0].details["field"] == "messages"


def test_stocktwits_adapter_warns_when_messages_payload_is_not_a_list() -> None:
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(
            json_fetcher=social__FakeJsonFetcher([{"messages": {"id": 123}}])
        ),
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_malformed_payload"]
    assert result.warnings[0].details["field"] == "messages"


def test_stocktwits_adapter_skips_all_malformed_messages_with_warning() -> None:
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(
            json_fetcher=social__FakeJsonFetcher(
                [
                    {
                        "messages": [
                            "not an object",
                            {"id": 1, "created_at": "2026-01-02T12:00:00Z"},
                            {
                                "id": 2,
                                "body": "Invalid timestamp",
                                "created_at": "not-a-date",
                            },
                        ]
                    }
                ]
            )
        ),
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)
    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["source_partial"]
    assert result.warnings[0].details == {
        "malformedMessageCount": "3",
        "provider": "stocktwits_public_stream",
        "source": "stocktwits",
    }


def test_stocktwits_adapter_preserves_valid_metrics_when_payload_is_mixed() -> None:
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(
            json_fetcher=social__FakeJsonFetcher(
                [
                    {
                        "messages": [
                            social__stocktwits_message(
                                message_id=1,
                                body="Bullish into earnings.",
                                created_at="2026-01-02T12:00:00Z",
                                sentiment="Bullish",
                            ),
                            {"id": 2, "created_at": "2026-01-02T12:01:00Z"},
                            social__stocktwits_message(
                                message_id=3,
                                body="No label, just watching.",
                                created_at="2026-01-02T12:02:00Z",
                                sentiment=None,
                            ),
                            social__stocktwits_message(
                                message_id=4,
                                body="Bearish below support.",
                                created_at="2026-01-02T12:03:00Z",
                                sentiment="Bearish",
                            ),
                            {"id": 5, "body": "Invalid timestamp", "created_at": "bad"},
                        ]
                    }
                ]
            )
        ),
    )
    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=10)
    assert [block.sentiment for block in result.source_blocks] == [
        "positive",
        None,
        "negative",
    ]
    metrics = {metric.name: metric.value for metric in result.metrics}
    assert metrics == {
        "message_count": Decimal("3"),
        "bullish_count": Decimal("1"),
        "bearish_count": Decimal("1"),
        "unlabeled_count": Decimal("1"),
        "bullish_ratio": Decimal("0.3333"),
        "bearish_ratio": Decimal("0.3333"),
    }
    assert [warning.code for warning in result.warnings] == ["source_partial"]
    assert result.warnings[0].details["malformedMessageCount"] == "2"


def test_social_sentiment_service_degrades_malformed_stocktwits_source() -> None:
    stocktwits = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(json_fetcher=social__FakeJsonFetcher([{}])),
    )
    service = SocialSentimentService(source_adapters=[stocktwits])
    payload = social__payload(service.get_social_sentiment_snapshot("NVDA", sources=["stocktwits"]))
    assert payload["sourceBlocks"] == []
    assert payload["metrics"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "social_sentiment_empty_source",
        "social_sentiment_provider_error",
        "social_sentiment_unavailable",
    ]
    assert warnings[1]["details"] == [
        {"key": "field", "value": "messages"},
        {"key": "operation", "value": "social_sentiment"},
        {"key": "provider", "value": "stocktwits_public_stream"},
        {"key": "source", "value": "stocktwits"},
        {"key": "symbol", "value": "NVDA"},
    ]


def test_social_adapter_aggregates_reddit_stocktwits_source_blocks_and_metrics() -> None:
    reddit_as_of = datetime(2026, 1, 2, 10, tzinfo=UTC)
    stocktwits_as_of = datetime(2026, 1, 2, 12, tzinfo=UTC)
    reddit = social__SocialAdapter(
        source="reddit",
        provider_name="reddit_fixture",
        blocks=[
            ProviderSocialSentimentSourceBlock(
                source="reddit",
                provider="reddit_fixture",
                title="Retail thread",
                summary="Discussion volume increased.",
                as_of=reddit_as_of,
                symbols=["nvda"],
                sentiment="positive",
                metrics=[
                    ProviderSocialSentimentMetric(
                        name="comment_count",
                        value=Decimal("18"),
                        unit="count",
                        source="reddit",
                        as_of=reddit_as_of,
                    )
                ],
            )
        ],
        metrics=[
            ProviderSocialSentimentMetric(
                name="mention_count",
                value=Decimal("1"),
                unit="count",
                source="reddit",
                as_of=reddit_as_of,
            )
        ],
    )
    stocktwits = social__SocialAdapter(
        source="stocktwits",
        provider_name="stocktwits_fixture",
        blocks=[
            ProviderSocialSentimentSourceBlock(
                source="stocktwits",
                provider="stocktwits_fixture",
                title="@trader",
                summary="Bullish into earnings.",
                as_of=stocktwits_as_of,
                symbols=["NVDA"],
                sentiment="positive",
                metrics=[
                    ProviderSocialSentimentMetric(
                        name="message_count",
                        value=Decimal("1"),
                        unit="count",
                        source="stocktwits",
                        as_of=stocktwits_as_of,
                    )
                ],
            )
        ],
        metrics=[
            ProviderSocialSentimentMetric(
                name="bullish_ratio",
                value=Decimal("1"),
                source="stocktwits",
                as_of=stocktwits_as_of,
            )
        ],
    )
    service = SocialSentimentService(source_adapters=[reddit, stocktwits])
    result = service.get_social_sentiment_snapshot(
        " nvda ",
        sources=["stocktwits", "reddit", "stocktwits"],
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 1, 3, tzinfo=UTC),
        item_limit=5,
    )
    payload = social__payload(result)
    assert payload["symbol"] == "NVDA"
    assert payload["sources"] == ["stocktwits", "reddit"]
    assert stocktwits.calls == [
        ("NVDA", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC), 6)
    ]
    source_blocks = cast(list[dict[str, object]], payload["sourceBlocks"])
    assert [block["source"] for block in source_blocks] == ["stocktwits", "reddit"]
    assert source_blocks[0]["provider"] == "stocktwits_fixture"
    assert source_blocks[1]["symbols"] == ["NVDA"]
    metrics = cast(list[dict[str, object]], payload["metrics"])
    assert {metric["name"] for metric in metrics} == {"bullish_ratio", "mention_count"}
    assert payload["warnings"] == []


def test_social_adapter_partial_result_warns_for_missing_source() -> None:
    reddit = social__SocialAdapter(
        source="reddit",
        provider_name="reddit_fixture",
        blocks=[
            ProviderSocialSentimentSourceBlock(
                source="reddit",
                provider="reddit_fixture",
                title="Only Reddit covered",
                as_of=datetime(2026, 1, 2, tzinfo=UTC),
                symbols=["NVDA"],
            )
        ],
    )
    service = SocialSentimentService(source_adapters=[reddit])
    payload = social__payload(
        service.get_social_sentiment_snapshot(
            "nvda", sources=["reddit", "stocktwits"], item_limit=5
        )
    )
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "social_sentiment_provider_unavailable",
        "social_sentiment_partial_result",
    ]
    assert warnings[1]["details"] == [
        {"key": "sources", "value": "reddit,stocktwits"},
        {"key": "symbol", "value": "NVDA"},
        {"key": "uncoveredSources", "value": "stocktwits"},
    ]


def test_social_adapter_rate_limit_degrades_without_raw_secret() -> None:
    stocktwits = social__SocialAdapter(
        source="stocktwits",
        provider_name="stocktwits_fixture",
        failure=SocialSentimentProviderRateLimitError(
            "stocktwits token=sk-secret rate limited",
            details={"status": "429", "api_key": "sk-secret"},
        ),
    )
    service = SocialSentimentService(source_adapters=[stocktwits])
    payload = social__payload(service.get_social_sentiment_snapshot("nvda", sources=["stocktwits"]))
    assert payload["sourceBlocks"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "social_sentiment_provider_rate_limited",
        "social_sentiment_unavailable",
    ]
    warning_json = json.dumps(warnings)
    assert "sk-secret" not in warning_json
    assert "apiKey" not in warning_json


def test_social_adapter_timeout_degrades_with_structured_warning() -> None:
    reddit = social__SocialAdapter(
        source="reddit",
        provider_name="reddit_fixture",
        failure=SocialSentimentProviderTimeoutError("reddit timed out"),
    )
    service = SocialSentimentService(source_adapters=[reddit])
    payload = social__payload(service.get_social_sentiment_snapshot("nvda", sources=["reddit"]))
    assert payload["sourceBlocks"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "social_sentiment_provider_timeout",
        "social_sentiment_unavailable",
    ]


def test_social_adapter_empty_result_returns_structured_warning() -> None:
    reddit = social__SocialAdapter(source="reddit", provider_name="reddit_fixture")
    service = SocialSentimentService(source_adapters=[reddit])
    payload = social__payload(service.get_social_sentiment_snapshot("nvda", sources=["reddit"]))
    assert payload["sourceBlocks"] == []
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "social_sentiment_empty_source",
        "social_sentiment_unavailable",
    ]


_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def social_contract__assert_json_safe_and_camel(payload: dict[str, object]) -> None:
    _ = json.dumps(payload)
    _assert_no_snake_case_keys(payload, path="$")


def _assert_no_snake_case_keys(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        payload = cast(dict[object, object], value)
        for key, nested_value in payload.items():
            assert isinstance(key, str)
            assert "_" not in key, f"snake_case key leaked at {path}.{key}"
            _assert_no_snake_case_keys(nested_value, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        payload = cast(list[object], value)
        for index, nested_value in enumerate(payload):
            _assert_no_snake_case_keys(nested_value, path=f"{path}[{index}]")


def test_social_sentiment_result_schema_normalizes_source_blocks_metrics_and_warnings() -> None:
    payload = RuntimeSocialSentimentLookupResult(
        symbol=" nvda ",
        sources=["Reddit", "stocktwits", "reddit"],
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=_NOW,
        source_blocks=[
            RuntimeSocialSentimentSourceBlock(
                source="Reddit",
                provider=" deterministic_fixture ",
                title=" Retail discussion ",
                summary=" Mentions increased. ",
                as_of=_NOW,
                symbols=[" nvda ", "NVDA"],
                sentiment="positive",
                metrics=[
                    RuntimeSocialSentimentMetric(
                        name="Mention Count",
                        value=Decimal("12"),
                        unit=" count ",
                        source="Reddit",
                        as_of=_NOW,
                    )
                ],
            )
        ],
        metrics=[RuntimeSocialSentimentMetric(name="Bullish Ratio", value=Decimal("0.67"))],
        warnings=[
            RuntimeToolWarning(
                code="source_partial",
                message="StockTwits returned a partial window.",
                details={"source": "stocktwits"},
            )
        ],
    ).model_dump(mode="json", by_alias=True)
    social_contract__assert_json_safe_and_camel(payload)
    assert payload["toolKey"] == SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["sources"] == ["reddit", "stocktwits"]
    assert payload["startDate"] == "2026-01-01T00:00:00Z"
    assert payload["endDate"] == "2026-01-02T03:04:05Z"
    source_blocks = cast(list[dict[str, object]], payload["sourceBlocks"])
    assert source_blocks[0]["source"] == "reddit"
    assert source_blocks[0]["provider"] == "deterministic_fixture"
    assert source_blocks[0]["symbols"] == ["NVDA"]
    block_metrics = cast(list[dict[str, object]], source_blocks[0]["metrics"])
    assert block_metrics[0] == {
        "name": "mention_count",
        "value": "12",
        "unit": "count",
        "source": "reddit",
        "asOf": "2026-01-02T03:04:05Z",
    }
    metrics = cast(list[dict[str, object]], payload["metrics"])
    assert metrics[0]["name"] == "bullish_ratio"
    assert cast(list[dict[str, object]], payload["warnings"])[0]["code"] == "source_partial"
    with pytest.raises(ValidationError, match="startDate must be before or equal to endDate"):
        _ = RuntimeSocialSentimentLookupResult(
            symbol="NVDA", start_date=_NOW, end_date=datetime(2026, 1, 1, tzinfo=UTC)
        )


def test_social_sentiment_parser_validation_normalizes_inputs_separately_from_news_lookup() -> None:
    social_arguments = parse_social_sentiment_lookup_arguments(
        json.dumps(
            {
                "symbol": " nvda ",
                "sources": ["StockTwits", "reddit", "stocktwits"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-02T03:04:05Z",
                "itemLimit": None,
            }
        )
    )
    news_arguments = parse_news_lookup_arguments(
        json.dumps(
            {
                "symbols": [" nvda "],
                "query": " social chatter ",
                "startDate": None,
                "endDate": None,
                "itemLimit": None,
            }
        )
    )
    assert social_arguments == {
        "symbol": "NVDA",
        "sources": ("stocktwits", "reddit"),
        "start_date": datetime(2026, 1, 1, tzinfo=UTC),
        "end_date": _NOW,
        "item_limit": 25,
    }
    assert news_arguments == {
        "symbols": ["NVDA"],
        "query": "social chatter",
        "scope": "symbol",
        "start_date": None,
        "end_date": None,
        "item_limit": 25,
    }
    assert "sources" not in news_arguments
    assert "query" not in social_arguments


@pytest.mark.parametrize(
    ("arguments", "expected_message"),
    [
        (
            {
                "symbol": "NVDA",
                "sources": ["forums"],
                "startDate": None,
                "endDate": None,
                "itemLimit": 2,
            },
            "signaldeck_finance_social_sentiment_lookup sources must use: reddit, stocktwits.",
        ),
        (
            {
                "symbol": "NVDA",
                "sources": None,
                "startDate": "2026-01-04",
                "endDate": "2026-01-03",
                "itemLimit": 2,
            },
            "signaldeck_finance_social_sentiment_lookup startDate must be before or "
            + "equal to endDate.",
        ),
        (
            {
                "symbol": " ",
                "sources": None,
                "startDate": None,
                "endDate": None,
                "itemLimit": 2,
            },
            "signaldeck_finance_social_sentiment_lookup symbol is required.",
        ),
        (
            {
                "symbol": "NVDA",
                "sources": None,
                "startDate": None,
                "endDate": None,
                "itemLimit": 51,
            },
            "signaldeck_finance_social_sentiment_lookup itemLimit must be at most 50.",
        ),
    ],
)
def test_social_sentiment_invalid_arguments_fail_deterministically(
    arguments: dict[str, object], expected_message: str
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_social_sentiment_lookup_arguments(json.dumps(arguments))
    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _assert_native_runtime_payload_is_json_safe_and_camel(payload: dict[str, object]) -> None:
    _ = json.dumps(payload)
    _assert_no_snake_case_keys(payload, path="$")


def _assert_no_snake_case_keys(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        payload = cast(dict[object, object], value)
        for key, nested_value in payload.items():
            assert isinstance(key, str)
            assert "_" not in key, f"snake_case key leaked at {path}.{key}"
            _assert_no_snake_case_keys(nested_value, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        payload = cast(list[object], value)
        for index, nested_value in enumerate(payload):
            _assert_no_snake_case_keys(nested_value, path=f"{path}[{index}]")


def finance_runtime__ohlcv_series() -> RuntimeOhlcvSeries:
    return RuntimeOhlcvSeries(
        symbol="NVDA",
        currency="USD",
        provider="deterministic_test",
        rows=[
            RuntimeOhlcvRow(
                at=datetime(2026, 1, 1, tzinfo=UTC),
                open=Decimal("118"),
                high=Decimal("121"),
                low=Decimal("117"),
                close=Decimal("119.75"),
                volume=1000,
                adjusted_close=Decimal("119.50"),
            ),
            RuntimeOhlcvRow(
                at=_NOW,
                open=Decimal("119.75"),
                high=Decimal("121.5"),
                low=Decimal("119"),
                close=Decimal("120.25"),
                volume=1200,
            ),
        ],
    )


def test_news_lookup_contract_uses_current_news_fields() -> None:
    parameters = NEWS_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], parameters["properties"])
    assert NEWS_LOOKUP_TOOL_SPEC.key == NEWS_LOOKUP_TOOL_KEY
    assert NEWS_LOOKUP_TOOL_SPEC.openai_function_name == NEWS_LOOKUP_OPENAI_FUNCTION_NAME
    assert list(properties) == [
        "symbols",
        "query",
        "scope",
        "startDate",
        "endDate",
        "itemLimit",
    ]
    assert parameters["required"] == [
        "symbols",
        "query",
        "scope",
        "startDate",
        "endDate",
        "itemLimit",
    ]
    assert cast(dict[str, object], properties["scope"])["enum"] == [
        "symbol",
        "market",
        "global",
        None,
    ]
    parsed = parse_news_lookup_arguments(
        json.dumps(
            {
                "symbols": [" nvda ", "NVDA"],
                "query": " earnings ",
                "scope": "symbol",
                "startDate": None,
                "endDate": None,
                "itemLimit": None,
            }
        )
    )
    assert parsed == {
        "symbols": ["NVDA"],
        "query": "earnings",
        "scope": "symbol",
        "start_date": None,
        "end_date": None,
        "item_limit": 25,
    }
    payload = RuntimeNewsLookupResult(
        symbols=["NVDA"],
        query="earnings",
        items=[RuntimeNewsItem(title="News", source="wire", published_at=_NOW)],
    ).model_dump(mode="json", by_alias=True)
    assert payload["toolKey"] == NEWS_LOOKUP_TOOL_KEY
    assert set(payload) == {
        "toolKey",
        "query",
        "symbols",
        "startDate",
        "endDate",
        "items",
        "warnings",
    }


def test_news_lookup_parser_supports_bounded_global_scope_without_social_mutation() -> None:
    parsed = parse_news_lookup_arguments(
        json.dumps(
            {
                "symbols": None,
                "query": "macro liquidity and export controls",
                "scope": " global ",
                "startDate": "2026-01-01T00:00:00Z",
                "endDate": "2026-01-03T00:00:00Z",
                "itemLimit": 10,
            }
        )
    )
    assert parsed == {
        "symbols": [],
        "query": "macro liquidity and export controls",
        "scope": "global",
        "start_date": datetime(2026, 1, 1, tzinfo=UTC),
        "end_date": datetime(2026, 1, 3, tzinfo=UTC),
        "item_limit": 10,
    }
    with pytest.raises(RuntimeToolError, match="scope must use: global, market, symbol"):
        _ = parse_news_lookup_arguments(
            json.dumps(
                {
                    "symbols": None,
                    "query": "markets",
                    "scope": "combined_sentiment",
                    "startDate": None,
                    "endDate": None,
                    "itemLimit": None,
                }
            )
        )
    with pytest.raises(RuntimeToolError, match="scope symbol requires symbols"):
        _ = parse_news_lookup_arguments(
            json.dumps(
                {
                    "symbols": None,
                    "query": "markets",
                    "scope": "symbol",
                    "startDate": None,
                    "endDate": None,
                    "itemLimit": None,
                }
            )
        )
    with pytest.raises(RuntimeToolError, match="query must be at most 240 characters"):
        _ = parse_news_lookup_arguments(
            json.dumps(
                {
                    "symbols": None,
                    "query": "x" * 241,
                    "scope": "global",
                    "startDate": None,
                    "endDate": None,
                    "itemLimit": None,
                }
            )
        )


def test_indicator_contract_requires_warmup_reasons_and_rejects_lookahead() -> None:
    with pytest.raises(ValidationError, match="nullReason is required"):
        _ = RuntimeIndicatorValue(name="sma_20", value=None)
    with pytest.raises(ValidationError, match="endDate cannot be after currentDate"):
        _ = RuntimeIndicatorLookupResult(
            symbol="NVDA",
            provider="deterministic_test",
            current_date=datetime(2026, 1, 2, tzinfo=UTC),
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 1, 3, tzinfo=UTC),
            rows=[],
        )


def test_ohlcv_contract_rejects_non_chronological_rows() -> None:
    with pytest.raises(ValidationError, match="Rows must be chronological"):
        _ = RuntimeOhlcvSeries(
            symbol="NVDA",
            provider="deterministic_test",
            rows=list(reversed(finance_runtime__ohlcv_series().rows)),
        )


def test_market_data_ohlcv_snapshot_normalizes_dedupes_bounds_and_utc_serializes(
    session_factory: sessionmaker[Session],
) -> None:
    provider = FakeFinanceProvider()
    start_date = datetime(2026, 1, 1, tzinfo=UTC)
    end_date = datetime(2026, 1, 3, 16, tzinfo=UTC)
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_ohlcv_snapshot(
            [" nvda ", "NVDA", "aapl"],
            start_date=start_date,
            end_date=end_date,
            row_limit=3,
        )
    assert provider.ohlcv_calls == [
        ("NVDA", start_date, end_date, "1d"),
        ("AAPL", start_date, end_date, "1d"),
    ]
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["startDate"] == "2026-01-01T00:00:00Z"
    assert payload["endDate"] == "2026-01-03T16:00:00Z"
    assert payload["warnings"] == []
    series = cast(list[dict[str, object]], payload["series"])
    assert [item["symbol"] for item in series] == ["NVDA", "AAPL"]
    rows = cast(list[dict[str, object]], series[0]["rows"])
    assert rows == [
        {
            "at": "2026-01-01T00:00:00Z",
            "open": "118.00",
            "high": "121.00",
            "low": "117.00",
            "close": "119.75",
            "volume": "1000",
            "adjustedClose": "119.50",
        },
        {
            "at": "2026-01-02T17:00:00Z",
            "open": "119.00",
            "high": "122.00",
            "low": "118.00",
            "close": "120.00",
            "volume": "1100",
            "adjustedClose": "119.80",
        },
        {
            "at": "2026-01-03T16:00:00Z",
            "open": "119.75",
            "high": "121.50",
            "low": "119.00",
            "close": "120.25",
            "volume": "1200",
            "adjustedClose": None,
        },
    ]


def test_market_data_ohlcv_snapshot_applies_row_limit(
    session_factory: sessionmaker[Session],
) -> None:
    provider = FakeFinanceProvider()
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_ohlcv_snapshot(
            ["nvda"],
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 1, 3, 16, tzinfo=UTC),
            row_limit=2,
        )
    payload = result.model_dump(mode="json", by_alias=True)
    series = cast(list[dict[str, object]], payload["series"])
    rows = cast(list[dict[str, object]], series[0]["rows"])
    assert [row["at"] for row in rows] == [
        "2026-01-02T17:00:00Z",
        "2026-01-03T16:00:00Z",
    ]


def test_market_data_ohlcv_snapshot_warns_for_unavailable_symbols_without_rows(
    session_factory: sessionmaker[Session],
) -> None:
    provider = FakeFinanceProvider(failing_symbols={"BAD"})
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_ohlcv_snapshot(
            ["bad", "nvda"],
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 1, 3, 16, tzinfo=UTC),
            row_limit=3,
        )
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    series = cast(list[dict[str, object]], payload["series"])
    assert [item["symbol"] for item in series] == ["NVDA"]
    assert payload["warnings"] == [
        {
            "code": "ohlcv_unavailable",
            "message": "No OHLCV data available for BAD",
            "details": [{"key": "symbol", "value": "BAD"}],
        }
    ]


def test_market_data_fundamentals_snapshot_uses_first_provider_success_and_utc_dates(
    session_factory: sessionmaker[Session],
) -> None:
    provider = FakeFinanceProvider(provider_name="fundamentals_primary")
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_fundamentals_snapshot(" nvda ", providers=[provider])
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.fundamental_calls == ["NVDA"]
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "fundamentals_primary"
    assert payload["asOf"] == "2026-01-02T17:00:00Z"
    assert payload["metrics"][0]["asOf"] == "2026-01-02T02:00:00Z"
    assert payload["statements"][0]["periodEnd"] == "2026-01-02T02:00:00Z"
    assert payload["warnings"] == []


def test_market_data_fundamentals_snapshot_falls_back_after_provider_failure(
    session_factory: sessionmaker[Session],
) -> None:
    failing_provider = FakeFinanceProvider(
        provider_name="fundamentals_failing",
        failure=QuoteProviderError(
            "primary fundamentals failed with api_key=sk-provider-secret",
            details={
                "provider_status": "503 sk-provider-secret",
                "api_key": "sk-provider-secret",
                "rawSecret": "hidden",
            },
        ),
    )
    success_provider = FakeFinanceProvider(provider_name="fundamentals_secondary")
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=failing_provider)
        result = service.get_fundamentals_snapshot(
            "nvda", providers=[failing_provider, success_provider]
        )
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert failing_provider.fundamental_calls == ["NVDA"]
    assert success_provider.fundamental_calls == ["NVDA"]
    assert payload["provider"] == "fundamentals_secondary"
    warning_json = json.dumps(payload["warnings"])
    assert "sk-provider-secret" not in warning_json
    assert "<redacted>" in warning_json
    assert payload["warnings"] == [
        {
            "code": "fundamentals_provider_error",
            "message": "primary fundamentals failed with api_key=<redacted>",
            "details": [
                {"key": "operation", "value": "fundamentals"},
                {"key": "provider", "value": "fundamentals_failing"},
                {"key": "providerStatus", "value": "503 <redacted>"},
            ],
        }
    ]


def test_market_data_fundamentals_snapshot_degrades_empty_for_all_provider_failures(
    session_factory: sessionmaker[Session],
) -> None:
    missing_key_provider = FakeFinanceProvider(
        provider_name="fundamentals_missing_key",
        failure=QuoteProviderMissingKeyError("fundamentals API key is missing"),
    )
    failing_provider = FakeFinanceProvider(
        provider_name="fundamentals_error",
        failure=QuoteProviderError("fundamentals provider failed"),
    )
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=missing_key_provider)
        result = service.get_fundamentals_snapshot(
            "nvda", providers=[missing_key_provider, failing_provider]
        )
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == ""
    assert payload["metrics"] == []
    assert payload["statements"] == []
    warning_payload = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warning_payload] == [
        "fundamentals_api_key_missing",
        "fundamentals_provider_error",
        "fundamentals_unavailable",
    ]


def test_market_data_news_snapshot_truncates_results_and_normalizes_dates(
    session_factory: sessionmaker[Session],
) -> None:
    provider = FakeFinanceProvider(provider_name="news_primary", news_count=4)
    start_date = datetime(2026, 1, 1, 19, tzinfo=timezone(timedelta(hours=-5)))
    end_date = datetime(2026, 1, 2, 19, tzinfo=timezone(timedelta(hours=-5)))
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_news_snapshot(
            symbols=[" nvda ", "NVDA"],
            query=" earnings ",
            start_date=start_date,
            end_date=end_date,
            item_limit=2,
            providers=[provider],
        )
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.news_calls == [
        (
            ["NVDA"],
            "earnings",
            "symbol",
            start_date.astimezone(UTC),
            end_date.astimezone(UTC),
            3,
        )
    ]
    assert payload["query"] == "earnings"
    assert payload["symbols"] == ["NVDA"]
    assert payload["startDate"] == "2026-01-02T00:00:00Z"
    assert payload["endDate"] == "2026-01-03T00:00:00Z"
    item_payload = cast(list[dict[str, object]], payload["items"])
    assert [item["title"] for item in item_payload] == ["News 3", "News 2"]
    assert payload["warnings"] == [
        {
            "code": "news_truncated",
            "message": "News results were truncated to 2 items",
            "details": [
                {"key": "limit", "value": "2"},
                {"key": "scope", "value": "symbol"},
            ],
        }
    ]


def test_market_data_news_snapshot_supports_global_scope_with_bounded_warning_and_dates(
    session_factory: sessionmaker[Session],
) -> None:
    provider = FakeFinanceProvider(provider_name="global_news", news_count=4)
    start_date = datetime(2026, 1, 2, 1, tzinfo=UTC)
    end_date = datetime(2026, 1, 2, 2, tzinfo=UTC)
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_news_snapshot(
            symbols=[],
            query="macro liquidity",
            scope="global",
            start_date=start_date,
            end_date=end_date,
            item_limit=10,
            providers=[provider],
        )
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.news_calls == [([], "macro liquidity", "global", start_date, end_date, 11)]
    assert payload["query"] == "macro liquidity"
    assert payload["symbols"] == []
    item_payload = cast(list[dict[str, object]], payload["items"])
    assert [item["title"] for item in item_payload] == ["News 2", "News 1"]
    assert payload["warnings"] == [
        {
            "code": "news_global_coverage_limited",
            "message": "Global news coverage is bounded by the configured finance provider",
            "details": [
                {"key": "provider", "value": "global_news"},
                {"key": "scope", "value": "global"},
            ],
        }
    ]


def test_market_data_news_snapshot_warns_for_empty_global_coverage(
    session_factory: sessionmaker[Session],
) -> None:
    provider = FakeFinanceProvider(provider_name="empty_global_news", news_count=0)
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_news_snapshot(
            query="macro liquidity", scope="global", providers=[provider]
        )
    payload = result.model_dump(mode="json", by_alias=True)
    assert payload["items"] == []
    assert payload["warnings"] == [
        {
            "code": "news_global_coverage_limited",
            "message": "Global news coverage is bounded by the configured finance provider",
            "details": [
                {"key": "provider", "value": "empty_global_news"},
                {"key": "scope", "value": "global"},
            ],
        },
        {
            "code": "news_empty",
            "message": "No news returned for the request",
            "details": [
                {"key": "provider", "value": "empty_global_news"},
                {"key": "query", "value": "macro liquidity"},
                {"key": "scope", "value": "global"},
                {"key": "symbols", "value": ""},
            ],
        },
    ]


def test_market_data_news_snapshot_bounds_provider_fallback_attempts(
    session_factory: sessionmaker[Session],
) -> None:
    providers = [
        FakeFinanceProvider(
            provider_name=f"news_failing_{index}",
            failure=QuoteProviderTimeoutError("news provider timed out"),
        )
        for index in range(4)
    ]
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=providers[0])
        result = service.get_news_snapshot(symbols=["nvda"], providers=providers)
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert [len(provider.news_calls) for provider in providers] == [1, 1, 1, 0]
    assert payload["items"] == []
    warning_payload = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warning_payload] == [
        "news_provider_timeout",
        "news_provider_timeout",
        "news_provider_timeout",
        "news_unavailable",
    ]


def test_market_data_insider_snapshot_truncates_and_utc_serializes(
    session_factory: sessionmaker[Session],
) -> None:
    provider = FakeFinanceProvider(provider_name="insider_primary", insider_count=3)
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_insider_transactions_snapshot(
            " nvda ",
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 1, 3, tzinfo=UTC),
            transaction_limit=2,
            providers=[provider],
        )
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.insider_calls == [
        ("NVDA", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC), 3)
    ]
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "insider_primary"
    transaction_payload = cast(list[dict[str, object]], payload["transactions"])
    assert [item["insiderName"] for item in transaction_payload] == [
        "Insider 2",
        "Insider 1",
    ]
    assert transaction_payload[0]["filedAt"] == "2026-01-03T02:00:00Z"
    assert transaction_payload[0]["transactionDate"] == "2026-01-02T02:00:00Z"
    assert payload["warnings"] == [
        {
            "code": "insider_truncated",
            "message": "Insider transactions were truncated to 2 rows",
            "details": [
                {"key": "limit", "value": "2"},
                {"key": "symbol", "value": "NVDA"},
            ],
        }
    ]


def test_market_data_indicator_snapshot_uses_bounded_ohlcv_without_lookahead(
    session_factory: sessionmaker[Session],
) -> None:
    provider = FakeFinanceProvider()
    start_date = datetime(2026, 1, 1, tzinfo=UTC)
    current_date = datetime(2026, 1, 3, 16, tzinfo=UTC)
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_indicator_snapshot(
            " nvda ",
            current_date=current_date,
            start_date=start_date,
            end_date=current_date,
            indicators=(MarketIndicatorSelection(indicator="sma", window=2),),
            row_limit=3,
        )
    assert provider.ohlcv_calls == [("NVDA", start_date, current_date, "1d")]
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "fake_runtime_provider"
    assert payload["currentDate"] == "2026-01-03T16:00:00Z"
    assert payload["startDate"] == "2026-01-01T00:00:00Z"
    assert payload["endDate"] == "2026-01-03T16:00:00Z"
    rows = cast(list[dict[str, object]], payload["rows"])
    assert [row["at"] for row in rows] == [
        "2026-01-01T00:00:00Z",
        "2026-01-02T17:00:00Z",
        "2026-01-03T16:00:00Z",
    ]
    row_1_values = {item["name"]: item for item in cast(list[dict[str, object]], rows[0]["values"])}
    assert row_1_values["close"] == {
        "name": "close",
        "value": "119.75",
        "nullReason": None,
    }
    assert row_1_values["sma_2"] == {
        "name": "sma_2",
        "value": None,
        "nullReason": "warmup",
    }
    assert rows[1]["values"] == [
        {"name": "close", "value": "120.00", "nullReason": None},
        {"name": "sma_2", "value": "119.875", "nullReason": None},
    ]
    assert rows[2]["values"] == [
        {"name": "close", "value": "120.25", "nullReason": None},
        {"name": "sma_2", "value": "120.125", "nullReason": None},
    ]
    assert "999" not in str(rows)


def test_market_data_indicator_snapshot_marks_insufficient_history_nulls(
    session_factory: sessionmaker[Session],
) -> None:
    provider = FakeFinanceProvider()
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_indicator_snapshot(
            "nvda",
            current_date=datetime(2026, 1, 3, 16, tzinfo=UTC),
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 1, 3, 16, tzinfo=UTC),
            indicators=(MarketIndicatorSelection(indicator="sma", window=5),),
            row_limit=3,
        )
    payload = result.model_dump(mode="json", by_alias=True)
    rows = cast(list[dict[str, object]], payload["rows"])
    for row in rows:
        values = cast(list[dict[str, object]], row["values"])
        assert values[1] == {
            "name": "sma_5",
            "value": None,
            "nullReason": "insufficient_history",
        }


def test_market_data_indicator_snapshot_rejects_invalid_bounds_and_future_rows(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FakeFinanceProvider()
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        with pytest.raises(QuoteProviderError, match="startDate must be before"):
            _ = service.get_indicator_snapshot(
                "nvda",
                current_date=datetime(2026, 1, 4, tzinfo=UTC),
                start_date=datetime(2026, 1, 4, tzinfo=UTC),
                end_date=datetime(2026, 1, 3, tzinfo=UTC),
                indicators=(MarketIndicatorSelection(indicator="sma", window=2),),
            )
        with pytest.raises(QuoteProviderError, match="endDate cannot be after currentDate"):
            _ = service.get_indicator_snapshot(
                "nvda",
                current_date=datetime(2026, 1, 2, tzinfo=UTC),
                start_date=datetime(2026, 1, 1, tzinfo=UTC),
                end_date=datetime(2026, 1, 3, tzinfo=UTC),
                indicators=(MarketIndicatorSelection(indicator="sma", window=2),),
            )
    assert provider.ohlcv_calls == []
    current_date = datetime(2026, 1, 3, tzinfo=UTC)

    def fake_get_ohlcv_snapshot(
        self: MarketDataService,
        symbols: list[str],
        *,
        start_date: datetime,
        end_date: datetime,
        row_limit: int | None = None,
    ) -> RuntimeOhlcvLookupResult:
        del self, symbols, row_limit
        return RuntimeOhlcvLookupResult(
            start_date=start_date,
            end_date=end_date,
            series=[
                RuntimeOhlcvSeries(
                    symbol="NVDA",
                    currency="USD",
                    provider="fake_runtime_provider",
                    rows=[
                        RuntimeOhlcvRow(
                            at=current_date + timedelta(minutes=1),
                            open=Decimal("100"),
                            high=Decimal("101"),
                            low=Decimal("99"),
                            close=Decimal("100"),
                            volume=1000,
                        )
                    ],
                )
            ],
        )

    monkeypatch.setattr(MarketDataService, "get_ohlcv_snapshot", fake_get_ohlcv_snapshot)
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        with pytest.raises(QuoteProviderError, match="cannot be after currentDate"):
            _ = service.get_indicator_snapshot(
                "nvda",
                current_date=current_date,
                start_date=current_date,
                end_date=current_date,
                indicators=(MarketIndicatorSelection(indicator="sma", window=2),),
            )


def test_market_data_ohlcv_snapshot_rejects_invalid_bounds_and_row_limits(
    session_factory: sessionmaker[Session],
) -> None:
    provider = FakeFinanceProvider()
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        with pytest.raises(QuoteProviderError, match="startDate must be before"):
            _ = service.get_ohlcv_snapshot(
                ["nvda"],
                start_date=datetime(2026, 1, 4, tzinfo=UTC),
                end_date=datetime(2026, 1, 3, tzinfo=UTC),
            )
        with pytest.raises(QuoteProviderError, match="rowLimit must be at least 1"):
            _ = service.get_ohlcv_snapshot(
                ["nvda"],
                start_date=datetime(2026, 1, 1, tzinfo=UTC),
                end_date=datetime(2026, 1, 3, tzinfo=UTC),
                row_limit=0,
            )
        with pytest.raises(QuoteProviderError, match="rowLimit must be at most 500"):
            _ = service.get_ohlcv_snapshot(
                ["nvda"],
                start_date=datetime(2026, 1, 1, tzinfo=UTC),
                end_date=datetime(2026, 1, 3, tzinfo=UTC),
                row_limit=501,
            )
    assert provider.ohlcv_calls == []


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        (
            "{",
            "OpenAI response requested signaldeck_finance_market_data_quote_lookup "
            + "with invalid JSON arguments.",
        ),
        (
            "[]",
            "signaldeck_finance_market_data_quote_lookup arguments must be a JSON object.",
        ),
        (
            '{"symbols":["NVDA"],"unsupported":true}',
            (
                "signaldeck_finance_market_data_quote_lookup arguments contained u"
                "nsupported fields: unsupported"
            ),
        ),
        ("{}", "signaldeck_finance_market_data_quote_lookup symbols is required."),
        (
            '{"symbols":"NVDA"}',
            "signaldeck_finance_market_data_quote_lookup symbols must be an array of strings.",
        ),
        (
            '{"symbols":[]}',
            "signaldeck_finance_market_data_quote_lookup symbols must contain at least one symbol.",
        ),
        (
            '{"symbols":["A","B","C","D","E","F","G","H","I","J","K"]}',
            "signaldeck_finance_market_data_quote_lookup symbols must contain at most 10 symbols.",
        ),
    ],
)
def test_market_data_quote_lookup_parser_preserves_validation_messages(
    arguments_json: str, expected_message: str
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_quote_lookup_arguments(arguments_json)
    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        (
            "{",
            "OpenAI response requested signaldeck_finance_market_data_history_lookup "
            + "with invalid JSON arguments.",
        ),
        (
            "[]",
            "signaldeck_finance_market_data_history_lookup arguments must be a JSON object.",
        ),
        (
            '{"symbols":["NVDA"],"unsupported":true}',
            (
                "signaldeck_finance_market_data_history_lookup arguments contained"
                " unsupported fields: unsupported"
            ),
        ),
        ("{}", "signaldeck_finance_market_data_history_lookup symbols is required."),
        (
            '{"symbols":["NVDA"],"range":"10y"}',
            "signaldeck_finance_market_data_history_lookup range must be one of 1mo, "
            + "3mo, ytd, 1y, or max.",
        ),
        (
            '{"symbols":["NVDA"],"pointLimit":"2"}',
            "signaldeck_finance_market_data_history_lookup pointLimit must be an integer.",
        ),
        (
            '{"symbols":["NVDA"],"pointLimit":251}',
            "signaldeck_finance_market_data_history_lookup pointLimit must be at most 250.",
        ),
    ],
)
def test_market_data_history_lookup_parser_preserves_validation_messages(
    arguments_json: str, expected_message: str
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_history_lookup_arguments(arguments_json)
    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


@pytest.mark.parametrize(
    ("parser", "arguments_json", "expected_arguments"),
    [
        (
            parse_ohlcv_lookup_arguments,
            json.dumps(
                {
                    "symbols": [" nvda ", "NVDA", "aapl"],
                    "startDate": "2026-01-01",
                    "endDate": "2026-01-03T16:00:00-05:00",
                    "rowLimit": 3,
                }
            ),
            {
                "symbols": ["NVDA", "AAPL"],
                "start_date": datetime(2026, 1, 1, tzinfo=UTC),
                "end_date": datetime(2026, 1, 3, 21, tzinfo=UTC),
                "row_limit": 3,
            },
        ),
        (
            parse_indicators_lookup_arguments,
            json.dumps(
                {
                    "symbol": " nvda ",
                    "currentDate": "2026-01-03T16:00:00Z",
                    "startDate": "2026-01-01",
                    "endDate": "2026-01-03T12:00:00-04:00",
                    "indicators": [
                        {"type": "SMA", "window": 20},
                        {"type": "ema", "window": 5},
                        {"type": "sma", "window": 20},
                    ],
                    "rowLimit": None,
                }
            ),
            {
                "symbol": "NVDA",
                "current_date": datetime(2026, 1, 3, 16, tzinfo=UTC),
                "start_date": datetime(2026, 1, 1, tzinfo=UTC),
                "end_date": datetime(2026, 1, 3, 16, tzinfo=UTC),
                "indicators": (
                    MarketIndicatorSelection(indicator="sma", window=20),
                    MarketIndicatorSelection(indicator="ema", window=5),
                ),
                "row_limit": 250,
            },
        ),
        (
            parse_fundamentals_lookup_arguments,
            json.dumps(
                {
                    "symbol": " nvda ",
                    "metricNames": [" Revenue_Growth ", "market_cap", "market_cap"],
                    "statementTypes": [" Income_Statement ", "cash_flow", "cash_flow"],
                    "periods": ["ANNUAL", "trailing_twelve_months"],
                    "statementLimit": 2,
                }
            ),
            {
                "symbol": "NVDA",
                "metric_names": ("revenue_growth", "market_cap"),
                "statement_types": ("income_statement", "cash_flow"),
                "periods": ("annual", "trailing_twelve_months"),
                "statement_limit": 2,
            },
        ),
        (
            parse_news_lookup_arguments,
            json.dumps(
                {
                    "symbols": [" nvda ", "AAPL", "NVDA"],
                    "query": " earnings ",
                    "startDate": "2026-01-01",
                    "endDate": None,
                    "itemLimit": 2,
                }
            ),
            {
                "symbols": ["NVDA", "AAPL"],
                "query": "earnings",
                "scope": "symbol",
                "start_date": datetime(2026, 1, 1, tzinfo=UTC),
                "end_date": None,
                "item_limit": 2,
            },
        ),
        (
            parse_social_sentiment_lookup_arguments,
            json.dumps(
                {
                    "symbol": " nvda ",
                    "sources": ["Reddit", "stocktwits", "reddit"],
                    "startDate": "2026-01-01",
                    "endDate": None,
                    "itemLimit": None,
                }
            ),
            {
                "symbol": "NVDA",
                "sources": ("reddit", "stocktwits"),
                "start_date": datetime(2026, 1, 1, tzinfo=UTC),
                "end_date": None,
                "item_limit": 25,
            },
        ),
        (
            parse_insider_data_lookup_arguments,
            json.dumps(
                {
                    "symbol": " nvda ",
                    "startDate": None,
                    "endDate": "2026-01-03T16:00:00+00:00",
                    "transactionLimit": None,
                }
            ),
            {
                "symbol": "NVDA",
                "start_date": None,
                "end_date": datetime(2026, 1, 3, 16, tzinfo=UTC),
                "transaction_limit": 50,
            },
        ),
    ],
)
def test_generic_platform_market_data_runtime_tool_parsers_normalize_happy_paths(
    parser: Callable[[str], dict[str, object]],
    arguments_json: str,
    expected_arguments: dict[str, object],
) -> None:
    assert parser(arguments_json) == expected_arguments


@pytest.mark.parametrize(
    (
        "spec",
        "tool_key",
        "function_name",
        "parser",
        "required",
        "property_names",
        "nested_check",
    ),
    [
        (
            INDICATORS_LOOKUP_TOOL_SPEC,
            INDICATORS_LOOKUP_TOOL_KEY,
            INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
            parse_indicators_lookup_arguments,
            ["symbol", "currentDate", "startDate", "endDate", "indicators", "rowLimit"],
            {"symbol", "currentDate", "startDate", "endDate", "indicators", "rowLimit"},
            (
                ("indicators", "type"),
                ["sma", "ema", "rsi", "macd", "bollinger_bands", "atr", "vwma"],
            ),
        ),
        (
            FUNDAMENTALS_LOOKUP_TOOL_SPEC,
            FUNDAMENTALS_LOOKUP_TOOL_KEY,
            FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
            parse_fundamentals_lookup_arguments,
            ["symbol", "metricNames", "statementTypes", "periods", "statementLimit"],
            {"symbol", "metricNames", "statementTypes", "periods", "statementLimit"},
            (
                ("metricNames",),
                [
                    "beta",
                    "current_ratio",
                    "debt_to_equity",
                    "dividend_yield",
                    "earnings_growth",
                    "enterprise_value",
                    "ev_to_ebitda",
                    "forward_pe",
                    "free_cash_flow_margin",
                    "gross_margin",
                    "market_cap",
                    "net_margin",
                    "operating_margin",
                    "price_to_book",
                    "price_to_sales",
                    "return_on_assets",
                    "return_on_equity",
                    "revenue_growth",
                    "trailing_pe",
                ],
            ),
        ),
    ],
)
def test_market_data_runtime_tool_specs_preserve_business_selection_schemas(
    spec: RuntimeToolSpec,
    tool_key: str,
    function_name: str,
    parser: Callable[[str], dict[str, object]],
    required: list[str],
    property_names: set[str],
    nested_check: tuple[tuple[str, ...], list[str]],
) -> None:
    assert spec.key == tool_key
    assert spec.openai_function_name == function_name
    assert spec.owner_extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    assert spec.parser is parser
    schema = spec.parameters_schema
    properties = cast(dict[str, object], schema["properties"])
    assert schema["required"] == required
    assert set(properties) == property_names
    path, expected_enum = nested_check
    property_schema = cast(dict[str, object], properties[path[0]])
    assert property_schema["type"] in ("array", ["array", "null"])
    item_schema = cast(dict[str, object], property_schema["items"])
    if len(path) == 2:
        item_properties = cast(dict[str, object], item_schema["properties"])
        enum_schema = cast(dict[str, object], item_properties[path[1]])
    else:
        enum_schema = item_schema
    assert enum_schema["enum"] == expected_enum


@pytest.mark.parametrize(
    ("parser", "function_name", "valid_arguments"),
    [
        (
            parse_ohlcv_lookup_arguments,
            MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbols": ["NVDA"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "rowLimit": 3,
            },
        ),
        (
            parse_indicators_lookup_arguments,
            INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-03",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "indicators": [{"type": "sma", "window": 2}],
                "rowLimit": 3,
            },
        ),
        (
            parse_fundamentals_lookup_arguments,
            FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbol": "NVDA",
                "metricNames": None,
                "statementTypes": None,
                "periods": None,
                "statementLimit": 3,
            },
        ),
        (
            parse_news_lookup_arguments,
            NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbols": ["NVDA"],
                "query": None,
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "itemLimit": 2,
            },
        ),
        (
            parse_social_sentiment_lookup_arguments,
            SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbol": "NVDA",
                "sources": None,
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "itemLimit": 2,
            },
        ),
        (
            parse_insider_data_lookup_arguments,
            INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbol": "NVDA",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "transactionLimit": 2,
            },
        ),
    ],
)
def test_generic_platform_market_data_runtime_tool_parsers_reject_boundary_payloads(
    parser: Callable[[str], dict[str, object]],
    function_name: str,
    valid_arguments: dict[str, object],
) -> None:
    with pytest.raises(RuntimeToolError) as invalid_json_error:
        _ = parser("{")
    assert invalid_json_error.value.code == "agent_tool_call_invalid"
    assert (
        invalid_json_error.value.message
        == f"OpenAI response requested {function_name} with invalid JSON arguments."
    )
    with pytest.raises(RuntimeToolError) as non_object_error:
        _ = parser("[]")
    assert non_object_error.value.code == "agent_tool_call_invalid"
    assert non_object_error.value.message == f"{function_name} arguments must be a JSON object."
    invalid_arguments = {**valid_arguments, "unsupported": True}
    with pytest.raises(RuntimeToolError) as unexpected_field_error:
        _ = parser(json.dumps(invalid_arguments))
    assert unexpected_field_error.value.code == "agent_tool_call_invalid"
    assert (
        unexpected_field_error.value.message
        == f"{function_name} arguments contained unsupported fields: unsupported"
    )


@pytest.mark.parametrize(
    ("parser", "arguments", "expected_message"),
    [
        (
            parse_ohlcv_lookup_arguments,
            {
                "symbols": ["NVDA"],
                "startDate": "2026-01-04",
                "endDate": "2026-01-03",
                "rowLimit": 3,
            },
            "signaldeck_finance_market_data_ohlcv_lookup startDate must be before or "
            + "equal to endDate.",
        ),
        (
            parse_ohlcv_lookup_arguments,
            {
                "symbols": ["A", "B", "C", "D", "E", "F"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "rowLimit": 3,
            },
            "signaldeck_finance_market_data_ohlcv_lookup symbols must contain at most 5 symbols.",
        ),
        (
            parse_ohlcv_lookup_arguments,
            {
                "symbols": ["NVDA"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "rowLimit": 501,
            },
            "signaldeck_finance_market_data_ohlcv_lookup rowLimit must be at most 500.",
        ),
        (
            parse_indicators_lookup_arguments,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-02",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "indicators": [{"type": "sma", "window": 2}],
                "rowLimit": 3,
            },
            "signaldeck_finance_indicators_lookup endDate cannot be after currentDate.",
        ),
        (
            parse_indicators_lookup_arguments,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-03",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "indicators": [{"type": "sma", "window": 2}],
                "rowLimit": 501,
            },
            "signaldeck_finance_indicators_lookup rowLimit must be at most 500.",
        ),
        (
            parse_indicators_lookup_arguments,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-03",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "indicators": [{"type": "stochastic", "window": 2}],
                "rowLimit": 3,
            },
            "signaldeck_finance_indicators_lookup indicator type must use: atr, "
            + "bollinger_bands, ema, macd, rsi, sma, vwma.",
        ),
        (
            parse_indicators_lookup_arguments,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-03",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "indicators": [
                    {
                        "type": "macd",
                        "fastWindow": 12,
                        "slowWindow": 12,
                        "signalWindow": 9,
                    }
                ],
                "rowLimit": 3,
            },
            "signaldeck_finance_indicators_lookup MACD fastWindow must be less than slowWindow.",
        ),
        (
            parse_fundamentals_lookup_arguments,
            {
                "symbol": "NVDA",
                "metricNames": None,
                "statementTypes": ["statement"],
                "periods": None,
                "statementLimit": 3,
            },
            "signaldeck_finance_fundamentals_lookup statementTypes must use: "
            + "balance_sheet, cash_flow, income_statement.",
        ),
        (
            parse_fundamentals_lookup_arguments,
            {
                "symbol": "NVDA",
                "metricNames": None,
                "statementTypes": None,
                "periods": ["daily"],
                "statementLimit": 3,
            },
            "signaldeck_finance_fundamentals_lookup periods must use: "
            + "annual, quarterly, trailing_twelve_months.",
        ),
        (
            parse_fundamentals_lookup_arguments,
            {
                "symbol": "NVDA",
                "metricNames": None,
                "statementTypes": None,
                "periods": None,
                "statementLimit": 13,
            },
            "signaldeck_finance_fundamentals_lookup statementLimit must be at most 12.",
        ),
        (
            parse_fundamentals_lookup_arguments,
            {
                "symbol": "NVDA",
                "metricNames": ["unsupported_metric"],
                "statementTypes": None,
                "periods": None,
                "statementLimit": 3,
            },
            "signaldeck_finance_fundamentals_lookup metricNames must use: beta, "
            + "current_ratio, debt_to_equity, dividend_yield, earnings_growth, "
            + "enterprise_value, ev_to_ebitda, forward_pe, free_cash_flow_margin, "
            + "gross_margin, market_cap, net_margin, operating_margin, price_to_book, "
            + "price_to_sales, return_on_assets, return_on_equity, revenue_growth, "
            + "trailing_pe.",
        ),
        (
            parse_news_lookup_arguments,
            {
                "symbols": ["NVDA"],
                "query": None,
                "startDate": "2026-01-04",
                "endDate": "2026-01-03",
                "itemLimit": 2,
            },
            "signaldeck_finance_news_lookup startDate must be before or equal to endDate.",
        ),
        (
            parse_news_lookup_arguments,
            {
                "symbols": ["A", "B", "C", "D", "E", "F"],
                "query": None,
                "startDate": None,
                "endDate": None,
                "itemLimit": 2,
            },
            "signaldeck_finance_news_lookup symbols must contain at most 5 symbols.",
        ),
        (
            parse_news_lookup_arguments,
            {
                "symbols": ["NVDA"],
                "query": None,
                "startDate": None,
                "endDate": None,
                "itemLimit": 51,
            },
            "signaldeck_finance_news_lookup itemLimit must be at most 50.",
        ),
        (
            parse_social_sentiment_lookup_arguments,
            {
                "symbol": "NVDA",
                "sources": ["forums"],
                "startDate": None,
                "endDate": None,
                "itemLimit": 2,
            },
            "signaldeck_finance_social_sentiment_lookup sources must use: reddit, stocktwits.",
        ),
        (
            parse_social_sentiment_lookup_arguments,
            {
                "symbol": "NVDA",
                "sources": None,
                "startDate": None,
                "endDate": None,
                "itemLimit": 51,
            },
            "signaldeck_finance_social_sentiment_lookup itemLimit must be at most 50.",
        ),
        (
            parse_insider_data_lookup_arguments,
            {
                "symbol": "NVDA",
                "startDate": "2026-01-04",
                "endDate": "2026-01-03",
                "transactionLimit": 2,
            },
            "signaldeck_finance_insider_data_lookup startDate must be before or equal to endDate.",
        ),
        (
            parse_insider_data_lookup_arguments,
            {
                "symbol": "NVDA",
                "startDate": None,
                "endDate": None,
                "transactionLimit": 101,
            },
            "signaldeck_finance_insider_data_lookup transactionLimit must be at most 100.",
        ),
    ],
)
def test_generic_platform_market_data_runtime_tool_parsers_reject_limits_and_bounds(
    parser: Callable[[str], dict[str, object]],
    arguments: dict[str, object],
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parser(json.dumps(arguments))
    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


@pytest.fixture()
def session_factory(database_url):
    from finance_plugin.models.base import Base
    from sqlalchemy import create_engine

    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture(autouse=True)
def _block_unmocked_finance_http(monkeypatch):
    def reject_request(*args, **kwargs):
        raise AssertionError("Provider tests must use an explicit transport fixture")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_request)


def test_market_data_quote_lookup_dispatches_to_service_with_injected_provider(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = FakeFinanceProvider(failing_symbols={"BAD"})
    payload = MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC.executor(
        RuntimeToolContext(session_factory=session_factory, quote_provider=quote_provider),
        MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC.parser('{"symbols":[" nvda ","NVDA","bad"]}'),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.quote_calls == ["NVDA", "BAD"]
    assert payload["toolKey"] == MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY
    quotes = cast(list[dict[str, object]], payload["quotes"])
    assert len(quotes) == 1
    assert quotes[0]["symbol"] == "NVDA"
    assert quotes[0]["previousClose"] == "119.75000000"
    assert quotes[0]["asOf"] == "2026-01-02T03:04:05Z"
    assert quotes[0]["isStale"] is True
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert warnings == [
        {
            "code": "quote_unavailable",
            "message": "No fresh quote available for BAD",
            "details": [{"key": "symbol", "value": "BAD"}],
        }
    ]


def test_market_data_history_lookup_dispatches_to_service_with_injected_provider(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = FakeFinanceProvider(failing_symbols={"BAD"})
    payload = MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC.executor(
        RuntimeToolContext(session_factory=session_factory, quote_provider=quote_provider),
        MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC.parser(
            '{"symbols":["nvda","bad"],"range":"3mo","pointLimit":2}'
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.history_calls == [("NVDA", "3mo", "1d"), ("BAD", "3mo", "1d")]
    assert payload["toolKey"] == MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY
    assert payload["range"] == "3mo"
    assert payload["interval"] == "1d"
    assert payload["startDate"] == "2026-01-02T00:00:00Z"
    assert payload["endDate"] == "2026-01-02T03:04:05Z"
    series = cast(list[dict[str, object]], payload["series"])
    assert len(series) == 1
    points = cast(list[dict[str, object]], series[0]["points"])
    assert points == [
        {"at": "2026-01-02T00:00:00Z", "close": "119.75"},
        {"at": "2026-01-02T03:04:05Z", "close": "120.25"},
    ]
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert warnings == [
        {
            "code": "history_unavailable",
            "message": "No history available for BAD",
            "details": [{"key": "symbol", "value": "BAD"}],
        }
    ]


def test_market_data_ohlcv_lookup_dispatches_to_service_with_injected_provider(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = FakeFinanceProvider()
    payload = MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC.executor(
        RuntimeToolContext(session_factory=session_factory, quote_provider=quote_provider),
        MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC.parser(
            json.dumps(
                {
                    "symbols": [" nvda ", "NVDA"],
                    "startDate": "2026-01-01",
                    "endDate": "2026-01-03T16:00:00Z",
                    "rowLimit": 2,
                }
            )
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.ohlcv_calls == [
        (
            "NVDA",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, 16, tzinfo=UTC),
            "1d",
        )
    ]
    assert payload["toolKey"] == MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY
    assert payload["startDate"] == "2026-01-01T00:00:00Z"
    assert payload["endDate"] == "2026-01-03T16:00:00Z"
    series = cast(list[dict[str, object]], payload["series"])
    assert len(series) == 1
    rows = cast(list[dict[str, object]], series[0]["rows"])
    assert [row["at"] for row in rows] == [
        "2026-01-02T17:00:00Z",
        "2026-01-03T16:00:00Z",
    ]
    assert rows[0]["open"] == "119.00"
    assert rows[0]["adjustedClose"] == "119.80"
    assert rows[1]["close"] == "120.25"
    assert payload["warnings"] == []


def test_indicators_lookup_dispatches_success_and_insufficient_history_nulls(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = FakeFinanceProvider()
    payload = INDICATORS_LOOKUP_TOOL_SPEC.executor(
        RuntimeToolContext(session_factory=session_factory, quote_provider=quote_provider),
        INDICATORS_LOOKUP_TOOL_SPEC.parser(
            json.dumps(
                {
                    "symbol": " nvda ",
                    "currentDate": "2026-01-03T16:00:00Z",
                    "startDate": "2026-01-01",
                    "endDate": "2026-01-03T16:00:00Z",
                    "indicators": [
                        {"type": "sma", "window": 2},
                        {"type": "ema", "window": 2},
                        {"type": "rsi", "window": 2},
                        {
                            "type": "macd",
                            "fastWindow": 1,
                            "slowWindow": 2,
                            "signalWindow": 2,
                        },
                        {
                            "type": "bollinger_bands",
                            "window": 2,
                            "standardDeviations": 2,
                        },
                        {"type": "atr", "window": 2},
                        {"type": "vwma", "window": 2},
                        {"type": "sma", "window": 5},
                        {"type": "sma", "window": 2},
                    ],
                    "rowLimit": 3,
                }
            )
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.ohlcv_calls == [
        (
            "NVDA",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, 16, tzinfo=UTC),
            "1d",
        )
    ]
    assert payload["toolKey"] == INDICATORS_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "fake_runtime_provider"
    rows = cast(list[dict[str, object]], payload["rows"])
    row_1_values = {item["name"]: item for item in cast(list[dict[str, object]], rows[0]["values"])}
    assert row_1_values["close"] == {
        "name": "close",
        "value": "119.75",
        "nullReason": None,
    }
    assert row_1_values["sma_2"] == {
        "name": "sma_2",
        "value": None,
        "nullReason": "warmup",
    }
    row_2_values = {item["name"]: item for item in cast(list[dict[str, object]], rows[1]["values"])}
    assert row_2_values["ema_2"] == {
        "name": "ema_2",
        "value": "119.875",
        "nullReason": None,
    }
    assert row_2_values["atr_2"] == {
        "name": "atr_2",
        "value": "4.00",
        "nullReason": None,
    }
    assert row_2_values["sma_5"] == {
        "name": "sma_5",
        "value": None,
        "nullReason": "insufficient_history",
    }
    row_3_values = {item["name"]: item for item in cast(list[dict[str, object]], rows[2]["values"])}
    assert row_3_values["sma_2"] == {
        "name": "sma_2",
        "value": "120.125",
        "nullReason": None,
    }
    assert row_3_values["ema_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["ema_2"]["value"])) == Decimal("120.125")
    assert row_3_values["rsi_2"] == {
        "name": "rsi_2",
        "value": "100",
        "nullReason": None,
    }
    assert row_3_values["macd_1_2_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["macd_1_2_2"]["value"])) == Decimal("0.125")
    assert row_3_values["macd_signal_1_2_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["macd_signal_1_2_2"]["value"])) == Decimal("0.125")
    assert row_3_values["macd_histogram_1_2_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["macd_histogram_1_2_2"]["value"])) == Decimal("0")
    assert row_3_values["bollinger_upper_2_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["bollinger_upper_2_2"]["value"])) == Decimal("120.375")
    assert row_3_values["bollinger_middle_2_2"] == {
        "name": "bollinger_middle_2_2",
        "value": "120.125",
        "nullReason": None,
    }
    assert row_3_values["bollinger_lower_2_2"] == {
        "name": "bollinger_lower_2_2",
        "value": "119.875",
        "nullReason": None,
    }
    assert row_3_values["atr_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["atr_2"]["value"])) == Decimal("3.25")
    assert row_3_values["vwma_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["vwma_2"]["value"])) == Decimal(
        "120.1304347826086956521739130"
    )
    assert payload["warnings"] == []


def test_fundamentals_lookup_dispatches_success_filters_and_limits_statements(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = FakeFinanceProvider(provider_name="fundamentals_primary")
    context = RuntimeToolContext(session_factory=session_factory, quote_provider=quote_provider)
    payload = FUNDAMENTALS_LOOKUP_TOOL_SPEC.executor(
        context,
        FUNDAMENTALS_LOOKUP_TOOL_SPEC.parser(
            json.dumps(
                {
                    "symbol": " nvda ",
                    "metricNames": None,
                    "statementTypes": None,
                    "periods": None,
                    "statementLimit": 3,
                }
            )
        ),
    )
    filtered_payload = FUNDAMENTALS_LOOKUP_TOOL_SPEC.executor(
        context,
        FUNDAMENTALS_LOOKUP_TOOL_SPEC.parser(
            json.dumps(
                {
                    "symbol": "NVDA",
                    "metricNames": ["free_cash_flow_margin", "revenue_growth"],
                    "statementTypes": ["cash_flow", "balance_sheet"],
                    "periods": ["quarterly", "trailing_twelve_months"],
                    "statementLimit": 1,
                }
            )
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    _assert_native_runtime_payload_is_json_safe_and_camel(filtered_payload)
    assert quote_provider.fundamental_calls == ["NVDA", "NVDA"]
    assert payload["toolKey"] == FUNDAMENTALS_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "fundamentals_primary"
    metrics = cast(list[dict[str, object]], payload["metrics"])
    assert [metric["name"] for metric in metrics] == [
        "market_cap",
        "revenue_growth",
        "free_cash_flow_margin",
    ]
    assert metrics[0] == {
        "name": "market_cap",
        "value": "1000000.50",
        "currency": "USD",
        "period": "ttm",
        "asOf": "2026-01-02T02:00:00Z",
    }
    statements = cast(list[dict[str, object]], payload["statements"])
    assert [statement["statementType"] for statement in statements] == [
        "income_statement",
        "balance_sheet",
        "cash_flow",
    ]
    assert [statement["period"] for statement in statements] == [
        "annual",
        "quarterly",
        "trailing_twelve_months",
    ]
    filtered_statements = cast(list[dict[str, object]], filtered_payload["statements"])
    filtered_metrics = cast(list[dict[str, object]], filtered_payload["metrics"])
    assert [metric["name"] for metric in filtered_metrics] == [
        "revenue_growth",
        "free_cash_flow_margin",
    ]
    assert filtered_statements == [
        {
            "statementType": "balance_sheet",
            "period": "quarterly",
            "periodEnd": "2025-11-01T02:00:00Z",
            "lines": [{"name": "assets", "value": "750000.00", "currency": "USD"}],
        }
    ]
    assert payload["warnings"] == []
    assert filtered_payload["warnings"] == []


def test_news_lookup_dispatches_success_and_truncates(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = FakeFinanceProvider(provider_name="news_primary", news_count=4)
    payload = NEWS_LOOKUP_TOOL_SPEC.executor(
        RuntimeToolContext(
            session_factory=session_factory,
            quote_provider=quote_provider,
            news_providers=[quote_provider],
        ),
        NEWS_LOOKUP_TOOL_SPEC.parser(
            json.dumps(
                {
                    "symbols": [" nvda ", "AAPL", "NVDA"],
                    "query": " earnings ",
                    "scope": "symbol",
                    "startDate": "2026-01-01T19:00:00-05:00",
                    "endDate": "2026-01-02T19:00:00-05:00",
                    "itemLimit": 2,
                }
            )
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.news_calls == [
        (
            ["NVDA", "AAPL"],
            "earnings",
            "symbol",
            datetime(2026, 1, 2, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
            3,
        )
    ]
    assert payload["toolKey"] == NEWS_LOOKUP_TOOL_KEY
    assert payload["symbols"] == ["NVDA", "AAPL"]
    assert payload["query"] == "earnings"
    items = cast(list[dict[str, object]], payload["items"])
    assert [item["title"] for item in items] == ["News 3", "News 2"]
    assert payload["warnings"] == [
        {
            "code": "news_truncated",
            "message": "News results were truncated to 2 items",
            "details": [
                {"key": "limit", "value": "2"},
                {"key": "scope", "value": "symbol"},
            ],
        }
    ]


def test_insider_data_lookup_dispatches_success_and_truncates(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = FakeFinanceProvider(provider_name="insider_primary", insider_count=3)
    payload = INSIDER_DATA_LOOKUP_TOOL_SPEC.executor(
        RuntimeToolContext(session_factory=session_factory, quote_provider=quote_provider),
        INSIDER_DATA_LOOKUP_TOOL_SPEC.parser(
            json.dumps(
                {
                    "symbol": " nvda ",
                    "startDate": "2026-01-01T00:00:00Z",
                    "endDate": "2026-01-03T00:00:00Z",
                    "transactionLimit": 2,
                }
            )
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.insider_calls == [
        ("NVDA", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC), 3)
    ]
    assert payload["toolKey"] == INSIDER_DATA_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "insider_primary"
    transactions = cast(list[dict[str, object]], payload["transactions"])
    assert [transaction["insiderName"] for transaction in transactions] == [
        "Insider 2",
        "Insider 1",
    ]
    assert payload["warnings"] == [
        {
            "code": "insider_truncated",
            "message": "Insider transactions were truncated to 2 rows",
            "details": [
                {"key": "limit", "value": "2"},
                {"key": "symbol", "value": "NVDA"},
            ],
        }
    ]


def test_fundamentals_lookup_provider_unavailable_returns_typed_empty_payload(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = FakeFinanceProvider(
        provider_name="unsupported_fundamentals",
        failure=QuoteProviderError(
            "Fundamentals unsupported",
            code="provider_unavailable",
            details={"provider": "unsupported_fundamentals", "symbol": "NVDA"},
        ),
    )
    payload = FUNDAMENTALS_LOOKUP_TOOL_SPEC.executor(
        RuntimeToolContext(session_factory=session_factory, quote_provider=quote_provider),
        FUNDAMENTALS_LOOKUP_TOOL_SPEC.parser(
            json.dumps(
                {
                    "symbol": "NVDA",
                    "metricNames": None,
                    "statementTypes": None,
                    "periods": None,
                    "statementLimit": 3,
                }
            )
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.fundamental_calls == ["NVDA"]
    assert payload["toolKey"] == FUNDAMENTALS_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == ""
    assert payload["metrics"] == []
    assert payload["statements"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "fundamentals_provider_unavailable",
        "fundamentals_unavailable",
    ]


def test_news_lookup_provider_unavailable_returns_typed_empty_payload(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = FakeFinanceProvider(
        provider_name="unsupported_news",
        failure=QuoteProviderError(
            "News unsupported",
            code="provider_unavailable",
            details={"provider": "unsupported_news", "symbols": "NVDA"},
        ),
    )
    payload = NEWS_LOOKUP_TOOL_SPEC.executor(
        RuntimeToolContext(
            session_factory=session_factory,
            quote_provider=quote_provider,
            news_providers=[quote_provider],
        ),
        NEWS_LOOKUP_TOOL_SPEC.parser(
            json.dumps(
                {
                    "symbols": ["NVDA"],
                    "query": "earnings",
                    "scope": "symbol",
                    "startDate": None,
                    "endDate": None,
                    "itemLimit": 2,
                }
            )
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.news_calls == [(["NVDA"], "earnings", "symbol", None, None, 3)]
    assert payload["toolKey"] == NEWS_LOOKUP_TOOL_KEY
    assert payload["symbols"] == ["NVDA"]
    assert payload["items"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "news_provider_unavailable",
        "news_unavailable",
    ]


def test_insider_data_lookup_provider_unavailable_returns_typed_empty_payload(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = FakeFinanceProvider(
        provider_name="unsupported_insider",
        failure=QuoteProviderError(
            "Insider unsupported",
            code="provider_unavailable",
            details={"provider": "unsupported_insider", "symbol": "NVDA"},
        ),
    )
    payload = INSIDER_DATA_LOOKUP_TOOL_SPEC.executor(
        RuntimeToolContext(session_factory=session_factory, quote_provider=quote_provider),
        INSIDER_DATA_LOOKUP_TOOL_SPEC.parser(
            json.dumps(
                {
                    "symbol": "NVDA",
                    "startDate": None,
                    "endDate": None,
                    "transactionLimit": 2,
                }
            )
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.insider_calls == [("NVDA", None, None, 3)]
    assert payload["toolKey"] == INSIDER_DATA_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == ""
    assert payload["transactions"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "insider_provider_unavailable",
        "insider_unavailable",
    ]


def test_quote_provider_failure_does_not_reuse_an_earlier_success(session_factory):
    provider = FakeFinanceProvider()
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        first, warnings = service.get_quote_snapshot("NVDA")
        assert first is not None and warnings == []
        provider.failing_symbols.add("NVDA")
        second, warnings = service.get_quote_snapshot("NVDA")
    assert second is None
    assert warnings == ["No fresh quote available for NVDA"]
    assert provider.quote_calls == ["NVDA", "NVDA"]


def test_alpha_news_provider_missing_key_degrades_with_structured_warning():
    provider = AlphaVantageNewsProvider(
        api_key=None, client=alpha__FakeAlphaClient(alpha__payload())
    )
    result = MarketDataService(
        session=None,
        quote_provider=DeterministicQuoteProvider(),
        news_providers=(provider,),
    ).get_news_snapshot(symbols=["NVDA"])
    payload = result.model_dump(mode="json", by_alias=True)
    assert payload["items"] == []
    assert [warning["code"] for warning in payload["warnings"]] == [
        "news_api_key_missing",
        "news_unavailable",
    ]
    assert "apiKey" not in json.dumps(payload["warnings"])


@pytest.mark.parametrize("has_provider", [True, False])
def test_social_executor_preserves_injected_data_or_structured_unavailability(
    has_provider,
):
    from finance_plugin.runtime_market_data import SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC

    def reject_session():
        raise AssertionError("Social provider execution has no database dependency")

    reddit = social__SocialAdapter(
        source="reddit",
        provider_name="reddit_fixture",
        blocks=[
            ProviderSocialSentimentSourceBlock(
                source="reddit",
                provider="reddit_fixture",
                title="Runtime path",
                as_of=datetime(2026, 1, 2, tzinfo=UTC),
                symbols=["NVDA"],
            ),
        ],
    )
    context = RuntimeToolContext(
        session_factory=reject_session,
        quote_provider=None,
        social_sentiment_adapters=(reddit,) if has_provider else (),
    )
    payload = SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC.executor(
        context,
        SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC.parser(
            json.dumps({"symbol": "nvda", "sources": ["reddit"], "itemLimit": 3})
        ),
    )
    assert payload["toolKey"] == SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY
    if has_provider:
        assert payload["sourceBlocks"][0]["title"] == "Runtime path"
        assert reddit.calls == [("NVDA", None, None, 4)]
    else:
        assert payload["sourceBlocks"] == []
        assert [warning["code"] for warning in payload["warnings"]] == [
            "social_sentiment_provider_unavailable",
            "social_sentiment_unavailable",
        ]


@pytest.fixture()
def finance_factory_settings(monkeypatch):
    from finance_plugin import provider_factory
    from finance_plugin.config import FinanceSettings

    for name, field in FinanceSettings.model_fields.items():
        monkeypatch.delenv(field.alias or name, raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    return FinanceSettings, provider_factory


def test_finance_factory_settings_normalize_provider_order_and_source_lists(
    finance_factory_settings,
):
    Settings, _ = finance_factory_settings
    settings = Settings.model_validate(
        {
            "FINANCE_NEWS_PROVIDER_ORDER": " Alpha_Vantage, yahoo, alpha_vantage ",
            "FINANCE_GLOBAL_NEWS_QUERIES": " markets, macro , markets ",
            "FINANCE_REDDIT_SUBREDDITS": " stocks, investing, stocks ",
        }
    )
    assert settings.news_provider_order == ["alpha_vantage", "yahoo"]
    assert settings.global_news_queries == ["markets", "macro"]
    assert settings.reddit_subreddits == ["stocks", "investing"]


@pytest.mark.parametrize(
    "config",
    [
        {"FINANCE_NEWS_PROVIDER_ORDER": "unknown"},
        {"FINANCE_NEWS_PROVIDER_ORDER": ""},
        {"FINANCE_NEWS_PROVIDER_ORDER": "alpha_vantage, deterministic"},
        {"QUOTE_PROVIDER_TIMEOUT": 0},
        {"FINANCE_REDDIT_RETRY_AFTER_MAX_SECONDS": -1},
    ],
)
def test_finance_factory_rejects_invalid_or_synthetic_fallback_config(
    finance_factory_settings, config
):
    Settings, _ = finance_factory_settings
    with pytest.raises(ValidationError):
        Settings.model_validate(config)


def test_finance_factory_keeps_yahoo_default_and_propagates_provider_controls(
    finance_factory_settings,
):
    Settings, factory = finance_factory_settings
    default = Settings()
    assert factory.create_quote_provider(default).__class__.__name__ == "YahooFinanceQuoteProvider"
    assert [provider.provider_name for provider in factory.create_news_providers(default)] == [
        "yahoo"
    ]
    configured = Settings.model_validate(
        {
            "QUOTE_PROVIDER_TIMEOUT": 3.5,
            "FINANCE_NEWS_PROVIDER_ORDER": "alpha_vantage,yahoo",
            "FINANCE_GLOBAL_NEWS_QUERIES": "markets,macro",
            "FINANCE_GLOBAL_NEWS_LOOKBACK_DAYS": 5,
            "FINANCE_REDDIT_SUBREDDITS": "stocks,investing",
            "FINANCE_REDDIT_RETRY_AFTER_MAX_SECONDS": 1.2,
            "FINANCE_REDDIT_INTER_REQUEST_DELAY_SECONDS": 0.3,
        }
    )
    assert factory.create_quote_provider(configured).timeout == 3.5
    alpha, yahoo = factory.create_news_providers(configured)
    assert [alpha.provider_name, yahoo.provider_name] == ["alpha_vantage", "yahoo"]
    assert alpha.timeout == yahoo.timeout == 3.5
    assert alpha.api_key is None
    assert yahoo.global_queries == ("markets", "macro")
    assert yahoo.global_lookback_days == 5
    reddit, stocktwits = factory.create_social_sentiment_adapters(configured)
    assert reddit.timeout == stocktwits.timeout == 3.5
    assert reddit.subreddits == ("stocks", "investing")
    assert reddit.retry_after_max_seconds == 1.2
    assert reddit.inter_request_delay_seconds == 0.3


@pytest.mark.parametrize(
    "config",
    [
        {"QUOTE_PROVIDER_BACKEND": " Deterministic "},
        {"FINANCE_NEWS_PROVIDER_ORDER": "deterministic"},
    ],
)
def test_finance_factory_deterministic_news_requires_explicit_test_choice(
    finance_factory_settings, config
):
    Settings, factory = finance_factory_settings
    settings = Settings.model_validate(config)
    assert [type(provider) for provider in factory.create_news_providers(settings)] == [
        DeterministicNewsProvider
    ]
    if settings.quote_provider_backend == "deterministic":
        assert isinstance(factory.create_quote_provider(settings), DeterministicQuoteProvider)


def test_finance_factory_secret_is_private_and_absent_from_effective_configuration(
    finance_factory_settings, monkeypatch
):
    Settings, factory = finance_factory_settings
    secret = "alpha-private-test-key"
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", secret)
    settings = Settings(FINANCE_NEWS_PROVIDER_ORDER="alpha_vantage")
    provider = factory.create_news_providers(settings)[0]
    assert provider.api_key == secret
    assert secret not in repr(provider)
    assert secret not in settings.model_dump_json()
    assert "ALPHA_VANTAGE_API_KEY" not in settings.model_dump(by_alias=True)


def test_finance_main_uses_configured_news_provider_and_binds_nonsecret_configuration(
    finance_factory_settings, monkeypatch
):
    from fastapi.testclient import TestClient
    from finance_plugin.main import create_app

    Settings, _ = finance_factory_settings
    observed = []

    def response(self, *, params):
        observed.append(dict(params))
        return alpha__payload()

    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "alpha-deployment-key")
    monkeypatch.setattr(
        "finance_plugin.providers.alpha_vantage_news_provider._AlphaVantageNewsHttpClient.fetch_news",
        response,
    )
    settings = Settings(
        FINANCE_NEWS_PROVIDER_ORDER="alpha_vantage,yahoo", QUOTE_PROVIDER_TIMEOUT=3.5
    )
    apps = []

    def build(config):
        app = create_app("postgresql+psycopg://unused:unused@127.0.0.1:1/unused", settings=config)
        apps.append(app)
        return app, TestClient(app).get("/release").json()

    try:
        app, first = build(settings)
        output = app.state.execute(
            "signaldeck/finance/news_lookup",
            {"symbols": ["NVDA"], "itemLimit": 1},
            {
                "resourceGrants": ["finance-market-data"],
                "resourceBindings": {"finance-market-data": {"allowedSymbols": ["NVDA"]}},
            },
        )
        assert observed[0]["apikey"] == "alpha-deployment-key"
        assert output["items"][0]["source"] == "Alpha Wire"
        monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "rotated-deployment-key")
        _, rotated = build(settings)
        _, changed = build(settings.model_copy(update={"quote_provider_timeout_seconds": 4.5}))
        assert first == rotated
        assert first["artifactDigest"] != changed["artifactDigest"]
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import ValidationError as SchemaValidationError

        indicator = next(
            tool for tool in first["tools"] if tool["toolId"].endswith("/indicators_lookup")
        )
        validator = Draft202012Validator(indicator["inputSchema"])
        valid = {
            "symbol": "NVDA",
            "currentDate": "2026-01-03",
            "startDate": "2026-01-01",
            "endDate": "2026-01-03",
            "indicators": [{"type": "bollinger_bands", "window": 2, "standardDeviations": 2.0}],
        }
        validator.validate(valid)
        with pytest.raises(SchemaValidationError):
            validator.validate(
                {
                    **valid,
                    "indicators": [
                        {"type": "bollinger_bands", "window": 2, "standardDeviations": "2"}
                    ],
                }
            )
        descriptor = json.dumps(first)
        assert (
            "alpha-deployment-key" not in descriptor and "rotated-deployment-key" not in descriptor
        )
    finally:
        for app in apps:
            app.state.engine.dispose()


@pytest.mark.parametrize("outcome", [200, 429, 503, "timeout", "malformed_json"])
def test_alpha_httpx_query_credential_is_absent_from_logs_and_errors(caplog, outcome):
    import logging
    import traceback

    from finance_plugin.providers.alpha_vantage_news_provider import _AlphaVantageNewsHttpClient

    secret = "alpha-http-private-key"
    requests = []

    def handle(request):
        requests.append(str(request.url))
        if outcome == "timeout":
            raise httpx.ReadTimeout("Timeout: " + str(request.url), request=request)
        if outcome == "malformed_json":
            return httpx.Response(200, text=secret + " is not JSON")
        return httpx.Response(
            outcome, json=alpha__payload() if outcome == 200 else {"Note": secret}
        )

    caplog.set_level(logging.DEBUG, logger="httpx")
    caplog.set_level(logging.DEBUG, logger="httpcore")
    provider = AlphaVantageNewsProvider(
        api_key=secret,
        client=_AlphaVantageNewsHttpClient(timeout=1, transport=httpx.MockTransport(handle)),
    )
    if outcome == 200:
        assert provider.fetch_news(
            symbols=["NVDA"], query=None, scope="symbol", start_date=None, end_date=None, limit=1
        ).items
    else:
        with pytest.raises(
            (
                NewsProviderRateLimitError,
                NewsProviderUnavailableError,
                NewsProviderTimeoutError,
                NewsProviderMalformedResponseError,
            )
        ) as failure:
            provider.fetch_news(
                symbols=["NVDA"],
                query=None,
                scope="symbol",
                start_date=None,
                end_date=None,
                limit=1,
            )
        assert secret not in str(failure.value)
        assert secret not in "".join(traceback.format_exception(failure.value))
    assert secret in requests[0]
    assert secret not in caplog.text
    assert "apikey=" not in caplog.text.lower()


@pytest.mark.parametrize("configured", [None, ()])
def test_finance_news_without_explicit_provider_never_fabricates_items(configured):
    service = MarketDataService(
        session=None, quote_provider=FakeFinanceProvider(), news_providers=configured
    )
    payload = service.get_news_snapshot(symbols=["NVDA"]).model_dump(mode="json", by_alias=True)
    assert payload["items"] == []
    assert payload["warnings"] == [
        {
            "code": "news_provider_unavailable",
            "message": "No news providers are configured",
            "details": [{"key": "operation", "value": "news"}],
        }
    ]
    assert "deterministic" not in json.dumps(payload)

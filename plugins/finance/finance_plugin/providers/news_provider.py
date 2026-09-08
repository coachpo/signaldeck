from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from importlib import import_module
from typing import TYPE_CHECKING, Literal, Protocol

from plugin_runtime.formatting import normalize_symbol


class NewsProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: str = code
        self.details: dict[str, str] = details or {}


class NewsProviderMissingKeyError(NewsProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_api_key_missing", details=details)


class NewsProviderTimeoutError(NewsProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_timeout", details=details)


class NewsProviderRateLimitError(NewsProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_rate_limited", details=details)


class NewsProviderUnavailableError(NewsProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_unavailable", details=details)


class NewsProviderMalformedResponseError(NewsProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_malformed_response", details=details)


class NewsProviderUnsupportedQueryError(NewsProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_unsupported_query", details=details)


NewsScope = Literal["symbol", "market", "global"]
NewsSentiment = Literal["positive", "neutral", "negative", "mixed"]


@dataclass(frozen=True, slots=True)
class ProviderNewsItem:
    title: str
    source: str
    published_at: datetime
    url: str | None = None
    summary: str | None = None
    symbols: list[str] | None = None
    sentiment: NewsSentiment | None = None


@dataclass(frozen=True, slots=True)
class ProviderNewsResult:
    provider: str
    items: list[ProviderNewsItem]


class NewsProvider(Protocol):
    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: NewsScope,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult: ...


class DeterministicNewsProvider:
    provider_name: str = "deterministic_test"

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
        del start_date, end_date
        normalized_symbols = _normalize_symbols(symbols)
        if not normalized_symbols:
            query_label = (query or scope).strip().replace("_", " ")
            return ProviderNewsResult(
                provider=self.provider_name,
                items=[
                    ProviderNewsItem(
                        title=f"{query_label} deterministic news update",
                        source="deterministic_test",
                        published_at=datetime.combine(
                            date(2024, 3, 29), datetime.min.time(), tzinfo=UTC
                        ),
                        symbols=[],
                        sentiment="neutral",
                    )
                ][:limit],
            )
        items = [
            ProviderNewsItem(
                title=f"{symbol} deterministic market update",
                source="deterministic_test",
                published_at=datetime.combine(date(2024, 3, 29), datetime.min.time(), tzinfo=UTC),
                symbols=[symbol],
                sentiment="neutral",
            )
            for symbol in normalized_symbols[:limit]
        ]
        return ProviderNewsResult(provider=self.provider_name, items=items)


def _normalize_symbols(symbols: list[str]) -> list[str]:
    normalized_symbols: list[str] = []
    seen_symbols: set[str] = set()
    for raw_symbol in symbols:
        symbol = normalize_symbol(raw_symbol)
        if not symbol or symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        normalized_symbols.append(symbol)
    return normalized_symbols


if TYPE_CHECKING:
    from finance_plugin.providers.alpha_vantage_news_provider import (
        AlphaVantageNewsClient,
        AlphaVantageNewsProvider,
    )
    from finance_plugin.providers.yahoo_news_provider import (
        YahooFinanceNewsProvider,
        YahooFinanceNewsSearchClient,
    )


def __getattr__(name: str) -> object:
    if name in {"AlphaVantageNewsClient", "AlphaVantageNewsProvider"}:
        alpha_vantage_news_provider = import_module(
            "finance_plugin.providers.alpha_vantage_news_provider"
        )
        return getattr(alpha_vantage_news_provider, name)
    if name in {"YahooFinanceNewsProvider", "YahooFinanceNewsSearchClient"}:
        yahoo_news_provider = import_module("finance_plugin.providers.yahoo_news_provider")
        return getattr(yahoo_news_provider, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AlphaVantageNewsProvider",
    "DeterministicNewsProvider",
    "NewsProvider",
    "NewsProviderError",
    "NewsProviderMalformedResponseError",
    "NewsProviderMissingKeyError",
    "NewsProviderRateLimitError",
    "NewsProviderTimeoutError",
    "NewsProviderUnavailableError",
    "NewsProviderUnsupportedQueryError",
    "NewsSentiment",
    "NewsScope",
    "ProviderNewsItem",
    "ProviderNewsResult",
    "AlphaVantageNewsClient",
    "YahooFinanceNewsProvider",
    "YahooFinanceNewsSearchClient",
]

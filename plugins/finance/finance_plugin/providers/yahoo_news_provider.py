from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol, cast

import httpx
from finance_plugin.providers.news_provider import (
    NewsProviderMalformedResponseError,
    NewsProviderRateLimitError,
    NewsProviderTimeoutError,
    NewsProviderUnavailableError,
    NewsScope,
    ProviderNewsItem,
    ProviderNewsResult,
    _normalize_symbols,
)
from finance_plugin.providers.yahoo_news_parsing import (
    article_has_provider_date,
    dedupe_global_news,
    default_start_date,
    extract_yahoo_news_items,
    in_news_window,
    parse_yahoo_article,
)
from plugin_runtime.formatting import to_utc, utcnow

_YAHOO_NEWS_SEARCH_URL: Final = "https://query2.finance.yahoo.com/v1/finance/search"
_YAHOO_DEFAULT_GLOBAL_QUERIES: Final = (
    "financial markets",
    "macro economy",
    "monetary policy",
)


class YahooFinanceNewsSearchClient(Protocol):
    def search_news(self, *, query: str, limit: int) -> list[dict[str, object]]: ...


@dataclass(frozen=True, slots=True)
class YahooFinanceNewsProvider:
    timeout: float = 5.0
    global_queries: Sequence[str] = _YAHOO_DEFAULT_GLOBAL_QUERIES
    global_lookback_days: int = 7
    search_client: YahooFinanceNewsSearchClient | None = None
    provider_name: str = "yahoo"

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
        normalized_symbols = _normalize_symbols(symbols)
        effective_end = to_utc(end_date) if end_date is not None else utcnow()
        effective_start = default_start_date(
            scope=scope,
            start_date=start_date,
            end_date=effective_end,
            lookback_days=self.global_lookback_days,
        )
        queries = self._search_queries(
            symbols=normalized_symbols,
            query=query,
            scope=scope,
        )
        client = self.search_client or _YahooFinanceNewsHttpSearchClient(timeout=self.timeout)
        items: list[ProviderNewsItem] = []
        for search_query in queries:
            articles = client.search_news(query=search_query, limit=limit)
            for article in articles:
                parsed_item = parse_yahoo_article(
                    article,
                    symbols=normalized_symbols,
                    fallback_published_at=effective_end,
                    provider_name=self.provider_name,
                )
                if parsed_item is None or not in_news_window(
                    parsed_item.published_at,
                    has_provider_date=article_has_provider_date(article),
                    start_date=effective_start,
                    end_date=effective_end,
                ):
                    continue
                items.append(parsed_item)

        if scope == "global":
            items = dedupe_global_news(items)
        items.sort(key=lambda item: to_utc(item.published_at), reverse=True)
        return ProviderNewsResult(provider=self.provider_name, items=items[:limit])

    def _search_queries(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: NewsScope,
    ) -> list[str]:
        normalized_query = query.strip() if query is not None and query.strip() else None
        if normalized_query is not None:
            return [normalized_query]
        if scope == "symbol":
            return symbols
        queries = [item.strip() for item in self.global_queries if item.strip()]
        return queries or list(_YAHOO_DEFAULT_GLOBAL_QUERIES)


@dataclass(frozen=True, slots=True)
class _YahooFinanceNewsHttpSearchClient:
    timeout: float

    def search_news(self, *, query: str, limit: int) -> list[dict[str, object]]:
        params: dict[str, str | int] = {
            "q": query,
            "quotesCount": 0,
            "newsCount": limit,
            "enableFuzzyQuery": "true",
        }
        headers = {"User-Agent": "signaldeck-backend/0.1"}
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(_YAHOO_NEWS_SEARCH_URL, params=params, headers=headers)
                _ = response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise NewsProviderTimeoutError(
                "Yahoo Finance news request timed out",
                details={"provider": "yahoo"},
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise NewsProviderRateLimitError(
                    "Yahoo Finance news request was rate limited",
                    details={"provider": "yahoo", "status": "429"},
                ) from exc
            raise NewsProviderUnavailableError(
                "Yahoo Finance news request failed",
                details={"provider": "yahoo", "status": str(exc.response.status_code)},
            ) from exc
        except httpx.HTTPError as exc:
            raise NewsProviderUnavailableError(
                "Yahoo Finance news request failed",
                details={"provider": "yahoo"},
            ) from exc

        try:
            payload = cast(object, response.json())
        except ValueError as exc:
            raise NewsProviderMalformedResponseError(
                "Yahoo Finance news payload was malformed",
                details={"provider": "yahoo"},
            ) from exc
        return extract_yahoo_news_items(payload)


__all__ = [
    "YahooFinanceNewsProvider",
    "YahooFinanceNewsSearchClient",
]

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Protocol, cast

import httpx
from finance_plugin.providers.news_provider import (
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
    _normalize_symbols,
)
from plugin_runtime.formatting import to_utc

_ALPHA_VANTAGE_NEWS_URL: Final = "https://www.alphavantage.co/query"
_ALPHA_VANTAGE_DEFAULT_TOPICS: Final = (
    "financial_markets",
    "economy_macro",
    "economy_monetary",
)


class AlphaVantageNewsClient(Protocol):
    def fetch_news(self, *, params: dict[str, str | int]) -> object: ...


@dataclass(frozen=True, slots=True)
class AlphaVantageNewsProvider:
    api_key: str | None = field(repr=False)
    timeout: float = 5.0
    client: AlphaVantageNewsClient | None = None
    provider_name: str = "alpha_vantage"

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
        if self.api_key is None or not self.api_key.strip():
            raise NewsProviderMissingKeyError(
                "Alpha Vantage news provider requires a configured API key",
                details={"provider": self.provider_name},
            )
        normalized_symbols = _normalize_symbols(symbols)
        params = self._request_params(
            symbols=normalized_symbols,
            query=query,
            scope=scope,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        client = self.client or _AlphaVantageNewsHttpClient(timeout=self.timeout)
        try:
            payload = client.fetch_news(params=params)
        except httpx.TimeoutException:
            raise NewsProviderTimeoutError(
                "Alpha Vantage news request timed out",
                details={"provider": self.provider_name},
            ) from None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise NewsProviderRateLimitError(
                    "Alpha Vantage news request was rate limited",
                    details={"provider": self.provider_name, "status": "429"},
                ) from None
            raise NewsProviderUnavailableError(
                "Alpha Vantage news request failed",
                details={"provider": self.provider_name, "status": str(exc.response.status_code)},
            ) from None
        except httpx.HTTPError:
            raise NewsProviderUnavailableError(
                "Alpha Vantage news request failed",
                details={"provider": self.provider_name},
            ) from None

        items = [
            item
            for feed_item in _extract_alpha_feed(payload, provider_name=self.provider_name)
            if (item := _parse_alpha_feed_item(feed_item)) is not None
        ]
        return ProviderNewsResult(provider=self.provider_name, items=items[:limit])

    def _request_params(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: NewsScope,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> dict[str, str | int]:
        normalized_query = query.strip() if query is not None and query.strip() else None
        if normalized_query is not None and not symbols:
            raise NewsProviderUnsupportedQueryError(
                "Alpha Vantage free-text news queries require symbols",
                details={"provider": self.provider_name},
            )
        params: dict[str, str | int] = {
            "function": "NEWS_SENTIMENT",
            "source": "signaldeck",
            "apikey": self.api_key or "",
            "limit": limit,
        }
        if symbols:
            params["tickers"] = ",".join(symbols)
        else:
            del normalized_query
            del scope
            params["topics"] = ",".join(_ALPHA_VANTAGE_DEFAULT_TOPICS)
        if start_date is not None:
            params["time_from"] = _format_alpha_datetime(start_date)
        if end_date is not None:
            params["time_to"] = _format_alpha_datetime(end_date)
        return params


class _CredentialSafeAlphaTransport(httpx.BaseTransport):
    def __init__(self, transport: httpx.BaseTransport) -> None:
        self.transport = transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return self.transport.handle_request(request)
        finally:
            # HTTPX logs this request after transport returns and attaches it to errors.
            # The real request has already used the provider-required query credential.
            request.url = request.url.copy_remove_param("apikey")

    def close(self) -> None:
        self.transport.close()


@dataclass(frozen=True, slots=True)
class _AlphaVantageNewsHttpClient:
    timeout: float
    transport: httpx.BaseTransport | None = None

    def fetch_news(self, *, params: dict[str, str | int]) -> object:
        transport = _CredentialSafeAlphaTransport(self.transport or httpx.HTTPTransport())
        with httpx.Client(timeout=self.timeout, transport=transport) as client:
            response = client.get(_ALPHA_VANTAGE_NEWS_URL, params=params)
            _ = response.raise_for_status()
            try:
                return cast(object, response.json())
            except ValueError:
                raise NewsProviderMalformedResponseError(
                    "Alpha Vantage news payload was malformed",
                    details={"provider": "alpha_vantage"},
                ) from None


def _extract_alpha_feed(payload: object, *, provider_name: str) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise NewsProviderMalformedResponseError(
            "Alpha Vantage news payload was malformed",
            details={"provider": provider_name},
        )
    note = _clean_string(payload.get("Note"))
    if note is not None:
        raise NewsProviderRateLimitError(
            "Alpha Vantage news provider was rate limited",
            details={"provider": provider_name},
        )
    information = _clean_string(payload.get("Information"))
    if information is not None:
        raise NewsProviderMissingKeyError(
            "Alpha Vantage news provider rejected the configured API key",
            details={"provider": provider_name},
        )
    feed = payload.get("feed")
    if not isinstance(feed, list):
        raise NewsProviderMalformedResponseError(
            "Alpha Vantage news payload was malformed",
            details={"provider": provider_name},
        )
    articles: list[dict[str, object]] = []
    for item in feed:
        if not isinstance(item, dict):
            raise NewsProviderMalformedResponseError(
                "Alpha Vantage news payload was malformed",
                details={"provider": provider_name},
            )
        articles.append(cast(dict[str, object], item))
    return articles


def _parse_alpha_feed_item(article: dict[str, object]) -> ProviderNewsItem | None:
    title = _clean_string(article.get("title"))
    source = _clean_string(article.get("source"))
    published_at = _parse_alpha_datetime(article.get("time_published"))
    if title is None or source is None or published_at is None:
        return None
    return ProviderNewsItem(
        title=title,
        source=source,
        published_at=published_at,
        url=_clean_string(article.get("url")),
        summary=_clean_string(article.get("summary")),
        symbols=_ticker_symbols(article.get("ticker_sentiment")),
        sentiment=_sentiment(article.get("overall_sentiment_label")),
    )


def _ticker_symbols(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    symbols: list[str] = []
    for item in value:
        if isinstance(item, dict):
            ticker = _clean_string(item.get("ticker"))
            if ticker is not None:
                symbols.append(ticker)
    return _normalize_symbols(symbols)


def _sentiment(value: object) -> NewsSentiment | None:
    label = _clean_string(value)
    if label is None:
        return None
    normalized = label.casefold().replace("_", "-").strip()
    if "positive" in normalized or "bullish" in normalized:
        return "positive"
    if "negative" in normalized or "bearish" in normalized:
        return "negative"
    if normalized == "neutral":
        return "neutral"
    return "mixed"


def _parse_alpha_datetime(value: object) -> datetime | None:
    raw_value = _clean_string(value)
    if raw_value is None:
        return None
    for pattern in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            return datetime.strptime(raw_value, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _format_alpha_datetime(value: datetime) -> str:
    return to_utc(value).strftime("%Y%m%dT%H%M")


def _clean_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


__all__ = ["AlphaVantageNewsClient", "AlphaVantageNewsProvider"]

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Final, cast

from finance_plugin.providers.news_provider import (
    NewsProviderMalformedResponseError,
    NewsScope,
    ProviderNewsItem,
)
from plugin_runtime.formatting import to_utc, utcnow

_TITLE_SPACE_RE: Final = re.compile(r"\s+")


def extract_yahoo_news_items(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise NewsProviderMalformedResponseError(
            "Yahoo Finance news payload was malformed",
            details={"provider": "yahoo"},
        )
    news_items = payload.get("news")
    if not isinstance(news_items, list):
        raise NewsProviderMalformedResponseError(
            "Yahoo Finance news payload was malformed",
            details={"provider": "yahoo"},
        )
    articles: list[dict[str, object]] = []
    for news_item in news_items:
        if not isinstance(news_item, dict):
            raise NewsProviderMalformedResponseError(
                "Yahoo Finance news payload was malformed",
                details={"provider": "yahoo"},
            )
        articles.append(cast(dict[str, object], news_item))
    return articles


def default_start_date(
    *,
    scope: NewsScope,
    start_date: datetime | None,
    end_date: datetime,
    lookback_days: int,
) -> datetime | None:
    if start_date is not None:
        return to_utc(start_date)
    if scope in {"market", "global"}:
        return end_date - timedelta(days=lookback_days)
    return None


def parse_yahoo_article(
    article: dict[str, object],
    *,
    symbols: list[str],
    fallback_published_at: datetime,
    provider_name: str,
) -> ProviderNewsItem | None:
    content = article.get("content")
    payload = cast(dict[str, object], content) if isinstance(content, dict) else article
    title = _clean_string(payload.get("title"))
    if title is None:
        return None
    return ProviderNewsItem(
        title=title,
        source=_article_source(article) or provider_name,
        published_at=article_published_at(article) or fallback_published_at,
        url=_article_url(article),
        summary=_clean_string(payload.get("summary")),
        symbols=list(symbols),
    )


def article_has_provider_date(article: dict[str, object]) -> bool:
    return article_published_at(article) is not None


def article_published_at(article: dict[str, object]) -> datetime | None:
    content = article.get("content")
    payload = cast(dict[str, object], content) if isinstance(content, dict) else article
    for key in (
        "providerPublishTime",
        "pubDate",
        "publishedAt",
        "published_at",
        "publishTime",
        "displayTime",
        "date",
    ):
        published_at = _parse_yahoo_datetime(payload.get(key))
        if published_at is not None:
            return published_at
    return None


def in_news_window(
    published_at: datetime,
    *,
    has_provider_date: bool,
    start_date: datetime | None,
    end_date: datetime,
) -> bool:
    if not has_provider_date:
        return _window_reaches_current_day(end_date)
    normalized_published_at = to_utc(published_at)
    if start_date is not None and normalized_published_at < start_date:
        return False
    return normalized_published_at <= end_date


def dedupe_global_news(items: list[ProviderNewsItem]) -> list[ProviderNewsItem]:
    deduped: list[ProviderNewsItem] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for item in items:
        url_key = item.url.strip().lower() if item.url is not None else ""
        title_key = _normalized_title(item.title)
        if url_key and url_key in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue
        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        deduped.append(item)
    return deduped


def _article_source(article: dict[str, object]) -> str | None:
    content = article.get("content")
    payload = cast(dict[str, object], content) if isinstance(content, dict) else article
    provider = payload.get("provider")
    if isinstance(provider, dict):
        return _clean_string(provider.get("displayName")) or _clean_string(provider.get("name"))
    return _clean_string(payload.get("publisher")) or _clean_string(provider)


def _article_url(article: dict[str, object]) -> str | None:
    content = article.get("content")
    payload = cast(dict[str, object], content) if isinstance(content, dict) else article
    for key in ("canonicalUrl", "clickThroughUrl"):
        url_object = payload.get(key)
        if isinstance(url_object, dict):
            url = _clean_string(url_object.get("url"))
            if url is not None:
                return url
    return _clean_string(payload.get("link")) or _clean_string(payload.get("url"))


def _parse_yahoo_datetime(value: object) -> datetime | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.isdigit():
            return datetime.fromtimestamp(int(normalized), tz=UTC)
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return to_utc(parsed)
    return None


def _window_reaches_current_day(end_date: datetime) -> bool:
    current_day_start = datetime.combine(utcnow().date(), datetime.min.time(), tzinfo=UTC)
    return end_date >= current_day_start


def _normalized_title(title: str) -> str:
    return _TITLE_SPACE_RE.sub(" ", title.strip().casefold())


def _clean_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None

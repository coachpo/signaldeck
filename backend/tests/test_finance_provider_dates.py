"""Provider publication windows must not turn retrieval time into source evidence."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "finance"):
    sys.path.insert(0, str(PLUGINS / directory))

from finance_plugin.providers.news_provider import (  # noqa: E402
    YahooFinanceNewsProvider,
)
from finance_plugin.providers.quote_provider import (  # noqa: E402
    DeterministicQuoteProvider,
)
from finance_plugin.providers.social_sentiment_provider import (  # noqa: E402
    RedditSocialSentimentAdapter,
    _RedditRequestConfig,
    _RedditTransport,
)
from finance_plugin.providers.social_sentiment_service import (  # noqa: E402
    SocialSentimentService,
)
from finance_plugin.services.market_data_service import MarketDataService  # noqa: E402

START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 1, 3, tzinfo=UTC)


def _reddit_adapter(
    feed: str, posts: list[dict[str, object]] | None = None
) -> tuple[RedditSocialSentimentAdapter, list[str]]:
    calls: list[str] = []

    def fetch_text(url: str, **kwargs: object) -> str:
        calls.append("rss")
        return feed

    def fetch_json(url: str, **kwargs: object) -> dict[str, object]:
        calls.append("json")
        return {"data": {"children": [{"data": post} for post in posts or []]}}

    return (
        RedditSocialSentimentAdapter(
            timeout=1,
            config=_RedditRequestConfig(subreddits=("stocks",)),
            transport=_RedditTransport(fetch_json, fetch_text, lambda _: None),
        ),
        calls,
    )


@pytest.mark.parametrize("format_name", ["atom", "rss"])
def test_reddit_filters_dates_before_limiting_and_keeps_inclusive_utc_bounds(
    format_name: str,
) -> None:
    entries = [
        ("future", "2026-01-04T00:00:00Z", "Sun, 04 Jan 2026 00:00:00 GMT"),
        ("old", "2025-12-31T23:59:59Z", "Wed, 31 Dec 2025 23:59:59 GMT"),
        ("unknown", "", ""),
        ("invalid", "not-a-date", "not-a-date"),
        ("start", "2026-01-01T02:00:00+02:00", "Thu, 01 Jan 2026 02:00:00 +0200"),
        ("end", "2026-01-03T00:00:00Z", "Sat, 03 Jan 2026 00:00:00 GMT"),
        ("overflow", "2026-01-02T00:00:00Z", "Fri, 02 Jan 2026 00:00:00 GMT"),
    ]
    if format_name == "atom":
        feed = (
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            + "".join(
                f"<entry><title>{title}</title><published>{atom}</published></entry>"
                for title, atom, _ in entries
            )
            + "</feed>"
        )
    else:
        feed = (
            "<rss><channel>"
            + "".join(
                f"<item><title>{title}</title><pubDate>{rss}</pubDate></item>"
                for title, _, rss in entries
            )
            + "</channel></rss>"
        )
    adapter, calls = _reddit_adapter(feed)

    result = adapter.fetch_source_blocks("NVDA", start_date=START, end_date=END, limit=2)

    assert [block.title for block in result.source_blocks] == ["start", "end"]
    assert [block.as_of for block in result.source_blocks] == [START, END]
    assert calls == ["rss"]


@pytest.mark.parametrize("date_element", ["", "<published>invalid</published>"])
def test_reddit_unbounded_unknown_dates_remain_unknown(date_element: str) -> None:
    adapter, calls = _reddit_adapter(f"<feed><entry>{date_element}</entry></feed>")

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=2)

    assert len(result.source_blocks) == 1
    assert result.source_blocks[0].as_of is None
    assert calls == ["rss"]


@pytest.mark.parametrize("updated", ["2026-01-04T00:00:00Z", "invalid"])
def test_reddit_cutoff_rejects_later_or_unknown_revisions_including_json_fallback(
    updated: str,
) -> None:
    feed = (
        "<feed><entry><title>revised</title><published>2026-01-02T00:00:00Z</published>"
        f"<updated>{updated}</updated></entry></feed>"
    )
    adapter, calls = _reddit_adapter(
        feed,
        [
            {
                "title": "revised",
                "created_utc": START.timestamp(),
                "edited": END.timestamp() + 1,
            },
            {"title": "unknown edit", "created_utc": START.timestamp(), "edited": True},
            {"title": "invalid creation", "created_utc": float("inf")},
            {"title": "original", "created_utc": START.timestamp(), "edited": False},
        ],
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=START, end_date=END, limit=5)

    assert calls == ["rss", "json"]
    assert [block.title for block in result.source_blocks] == ["original"]


def test_reddit_cutoff_accepts_revision_available_at_boundary() -> None:
    adapter, calls = _reddit_adapter(
        "<feed><entry><published>2026-01-02T00:00:00Z</published>"
        "<updated>2026-01-03T02:00:00+02:00</updated></entry></feed>"
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=START, end_date=END, limit=5)

    assert len(result.source_blocks) == 1
    assert result.source_blocks[0].as_of == datetime(2026, 1, 2, tzinfo=UTC)
    assert calls == ["rss"]


@pytest.mark.parametrize("start,end", [(START, None), (None, END), (START, END)])
def test_reddit_unknown_dates_cannot_satisfy_a_window_and_empty_result_is_disclosed(
    start: datetime | None, end: datetime | None
) -> None:
    adapter, calls = _reddit_adapter(
        "<feed><entry><title>unknown</title></entry></feed>",
        [{"title": "unknown fallback"}],
    )

    result = SocialSentimentService([adapter]).get_social_sentiment_snapshot(
        "NVDA", sources=["reddit"], start_date=start, end_date=end
    )

    assert calls == ["rss", "json"]
    assert result.source_blocks == []
    assert "social_sentiment_empty_source" in [warning.code for warning in result.warnings]


class _NewsClient:
    def __init__(self, articles: list[dict[str, object]]) -> None:
        self.articles = articles

    def search_news(self, *, query: str, limit: int) -> list[dict[str, object]]:
        return self.articles


@pytest.mark.parametrize("keep_valid", [False, True])
def test_yahoo_missing_or_invalid_publication_dates_are_excluded_and_disclosed(
    keep_valid: bool,
) -> None:
    articles: list[dict[str, object]] = [
        {"title": "Undated"},
        {"title": "Invalid", "pubDate": "not-a-date"},
        {"title": "Overflow", "providerPublishTime": float("inf")},
        {
            "title": "Overflow string",
            "providerPublishTime": "9999999999999999999999999999",
        },
    ]
    today = datetime.now(UTC)
    published = today - timedelta(hours=1)
    if keep_valid:
        articles.append({"title": "Dated", "pubDate": published.isoformat()})
    provider = YahooFinanceNewsProvider(search_client=_NewsClient(articles))
    with Session() as session:
        service = MarketDataService(session, DeterministicQuoteProvider(), [provider])
        result = service.get_news_snapshot(
            symbols=["NVDA"], start_date=today - timedelta(days=1), end_date=today
        )

    assert [item.title for item in result.items] == (["Dated"] if keep_valid else [])
    if keep_valid:
        assert result.items[0].published_at == published
    codes = [warning.code for warning in result.warnings]
    assert "news_publication_date_unavailable" in codes
    assert ("news_empty" in codes) is (not keep_valid)
    warning = result.warnings[0]
    assert warning.details == {"excludedItemCount": "4", "provider": "yahoo"}

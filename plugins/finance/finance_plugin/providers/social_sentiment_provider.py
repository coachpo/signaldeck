from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Literal, Protocol, cast
from xml.etree import ElementTree

import httpx
from plugin_runtime.formatting import normalize_symbol, to_utc

SocialSentimentSource = Literal["reddit", "stocktwits"]


class SocialSentimentProviderError(Exception):
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


class SocialSentimentProviderTimeoutError(SocialSentimentProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_timeout", details=details)


class SocialSentimentProviderRateLimitError(SocialSentimentProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_rate_limited", details=details)


@dataclass(frozen=True, slots=True)
class ProviderSocialSentimentMetric:
    name: str
    value: Decimal | str | None
    unit: str | None = None
    source: str | None = None
    as_of: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProviderSocialSentimentSourceBlock:
    source: SocialSentimentSource
    provider: str
    title: str | None = None
    summary: str | None = None
    url: str | None = None
    as_of: datetime | None = None
    symbols: list[str] = field(default_factory=list)
    sentiment: Literal["positive", "neutral", "negative", "mixed"] | None = None
    metrics: list[ProviderSocialSentimentMetric] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProviderSocialSentimentWarning:
    code: str
    message: str
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderSocialSentimentSourceResult:
    source: SocialSentimentSource
    provider: str
    source_blocks: list[ProviderSocialSentimentSourceBlock] = field(default_factory=list)
    metrics: list[ProviderSocialSentimentMetric] = field(default_factory=list)
    warnings: list[ProviderSocialSentimentWarning] = field(default_factory=list)


class SocialSentimentSourceAdapter(Protocol):
    source: SocialSentimentSource
    provider_name: str

    def fetch_source_blocks(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderSocialSentimentSourceResult: ...


class _JsonFetcher(Protocol):
    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str | int],
        timeout: float,
        provider: str,
        source: SocialSentimentSource,
    ) -> dict[str, object]: ...


class _TextFetcher(Protocol):
    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str | int],
        timeout: float,
        provider: str,
        source: SocialSentimentSource,
    ) -> str: ...


class _Sleeper(Protocol):
    def __call__(self, delay_seconds: float, /) -> None: ...


class RedditSocialSentimentAdapter:
    source: SocialSentimentSource = "reddit"
    provider_name: str = "reddit_public_search"
    _API: str = "https://www.reddit.com/r/{subreddit}/search.json"
    _RSS_API: str = "https://www.reddit.com/r/{subreddit}/search.rss"
    _USER_AGENT: str = "signaldeck-backend/0.1"

    def __init__(
        self,
        *,
        timeout: float,
        config: _RedditRequestConfig | None = None,
        transport: _RedditTransport | None = None,
    ) -> None:
        request_config = config or _RedditRequestConfig()
        self.timeout: float = timeout
        self.subreddits: tuple[str, ...] = request_config.subreddits
        self.retry_after_max_seconds: float = max(0.0, request_config.retry_after_max_seconds)
        self.inter_request_delay_seconds: float = max(
            0.0, request_config.inter_request_delay_seconds
        )
        self._transport: _RedditTransport = transport or _RedditTransport(
            json_fetcher=_request_json,
            text_fetcher=_request_text,
            sleep=time.sleep,
        )

    def fetch_source_blocks(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderSocialSentimentSourceResult:
        normalized_symbol = normalize_symbol(symbol)
        blocks: list[ProviderSocialSentimentSourceBlock] = []
        warnings: list[ProviderSocialSentimentWarning] = []
        limit_per_subreddit = max(1, (limit + len(self.subreddits) - 1) // len(self.subreddits))

        for subreddit_index, subreddit in enumerate(self.subreddits):
            try:
                rss_blocks = self._fetch_subreddit_rss_blocks(
                    normalized_symbol,
                    subreddit=subreddit,
                    limit=limit_per_subreddit,
                )
                if rss_blocks:
                    blocks.extend(rss_blocks)
                    self._sleep_between_subreddits(subreddit_index)
                    continue
            except SocialSentimentProviderRateLimitError as exc:
                warnings.append(
                    _warning_from_error(
                        _error_with_subreddit(exc, subreddit=subreddit),
                        source=self.source,
                        provider=self.provider_name,
                    )
                )
                self._sleep_between_subreddits(subreddit_index)
                continue
            except SocialSentimentProviderError:
                rss_blocks = []

            try:
                posts = self._fetch_subreddit_posts(
                    normalized_symbol,
                    subreddit=subreddit,
                    limit=limit_per_subreddit,
                )
            except SocialSentimentProviderError as exc:
                warnings.append(
                    _warning_from_error(
                        _error_with_subreddit(exc, subreddit=subreddit),
                        source=self.source,
                        provider=self.provider_name,
                    )
                )
                self._sleep_between_subreddits(subreddit_index)
                continue
            for post in posts:
                block = self._build_post_block(
                    post,
                    symbol=normalized_symbol,
                    start_date=start_date,
                    end_date=end_date,
                )
                if block is not None:
                    blocks.append(block)
            self._sleep_between_subreddits(subreddit_index)

        filtered_blocks = blocks[:limit]
        metrics = (
            []
            if not filtered_blocks or any(not block.metrics for block in filtered_blocks)
            else _count_metrics(
                source=self.source,
                as_of=_latest_as_of(filtered_blocks),
                count=len(filtered_blocks),
            )
        )
        return ProviderSocialSentimentSourceResult(
            source=self.source,
            provider=self.provider_name,
            source_blocks=filtered_blocks,
            metrics=metrics,
            warnings=warnings,
        )

    def _fetch_subreddit_posts(
        self,
        symbol: str,
        *,
        subreddit: str,
        limit: int,
    ) -> list[dict[str, object]]:
        params: dict[str, str | int] = {
            "q": symbol,
            "restrict_sr": "on",
            "sort": "new",
            "t": "week",
            "limit": limit,
        }
        payload = self._transport.json_fetcher(
            self._API.format(subreddit=subreddit),
            params=params,
            timeout=self.timeout,
            provider=self.provider_name,
            source=self.source,
        )
        data = _object_dict(payload.get("data"))
        children = _object_list(data.get("children"))
        posts: list[dict[str, object]] = []
        for child in children:
            child_payload = _object_dict(child)
            post = _object_dict(child_payload.get("data"))
            posts.append(post)
        return posts

    def _fetch_subreddit_rss_blocks(
        self,
        symbol: str,
        *,
        subreddit: str,
        limit: int,
    ) -> list[ProviderSocialSentimentSourceBlock]:
        params: dict[str, str | int] = {
            "q": symbol,
            "restrict_sr": "on",
            "sort": "new",
            "t": "week",
            "limit": limit,
        }
        payload = self._fetch_subreddit_rss_text(subreddit=subreddit, params=params)
        return _parse_reddit_rss_blocks(
            payload,
            symbol=symbol,
            source=self.source,
            provider=self.provider_name,
            limit=limit,
        )

    def _fetch_subreddit_rss_text(
        self,
        *,
        subreddit: str,
        params: dict[str, str | int],
    ) -> str:
        try:
            return self._transport.text_fetcher(
                self._RSS_API.format(subreddit=subreddit),
                params=params,
                timeout=self.timeout,
                provider=self.provider_name,
                source=self.source,
            )
        except SocialSentimentProviderRateLimitError as exc:
            self._transport.sleep(self._retry_after_delay(exc))
            return self._transport.text_fetcher(
                self._RSS_API.format(subreddit=subreddit),
                params=params,
                timeout=self.timeout,
                provider=self.provider_name,
                source=self.source,
            )

    def _retry_after_delay(self, error: SocialSentimentProviderRateLimitError) -> float:
        raw_delay = error.details.get("retryAfterSeconds") or error.details.get("retryAfter")
        if raw_delay is None:
            return min(1.0, self.retry_after_max_seconds)
        try:
            parsed_delay = float(raw_delay)
        except ValueError:
            return min(1.0, self.retry_after_max_seconds)
        return min(max(0.0, parsed_delay), self.retry_after_max_seconds)

    def _sleep_between_subreddits(self, subreddit_index: int) -> None:
        if self.inter_request_delay_seconds <= 0:
            return
        if subreddit_index >= len(self.subreddits) - 1:
            return
        self._transport.sleep(self.inter_request_delay_seconds)

    def _build_post_block(
        self,
        post: dict[str, object],
        *,
        symbol: str,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> ProviderSocialSentimentSourceBlock | None:
        as_of = _unix_datetime(post.get("created_utc"))
        if not _within_bounds(as_of, start_date=start_date, end_date=end_date):
            return None
        title = _text(post.get("title"))
        summary = _truncate(_text(post.get("selftext")), limit=280)
        permalink = _text(post.get("permalink"))
        score = _decimal_int(post.get("score"))
        comments = _decimal_int(post.get("num_comments"))
        return ProviderSocialSentimentSourceBlock(
            source=self.source,
            provider=self.provider_name,
            title=title,
            summary=summary,
            url=f"https://www.reddit.com{permalink}" if permalink is not None else None,
            as_of=as_of,
            symbols=[symbol],
            metrics=[
                ProviderSocialSentimentMetric(
                    name="score",
                    value=score,
                    unit="count",
                    source=self.source,
                    as_of=as_of,
                ),
                ProviderSocialSentimentMetric(
                    name="comment_count",
                    value=comments,
                    unit="count",
                    source=self.source,
                    as_of=as_of,
                ),
            ],
        )


class StockTwitsSocialSentimentAdapter:
    source: SocialSentimentSource = "stocktwits"
    provider_name: str = "stocktwits_public_stream"
    _API: str = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"

    def __init__(self, *, timeout: float, transport: _StockTwitsTransport | None = None) -> None:
        self.timeout: float = timeout
        self._transport: _StockTwitsTransport = transport or _StockTwitsTransport(
            json_fetcher=_request_json
        )

    def fetch_source_blocks(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderSocialSentimentSourceResult:
        normalized_symbol = normalize_symbol(symbol)
        try:
            payload = self._transport.json_fetcher(
                self._API.format(symbol=normalized_symbol),
                params={},
                timeout=self.timeout,
                provider=self.provider_name,
                source=self.source,
            )
        except SocialSentimentProviderError as exc:
            return ProviderSocialSentimentSourceResult(
                source=self.source,
                provider=self.provider_name,
                warnings=[
                    _warning_from_error(
                        exc,
                        source=self.source,
                        provider=self.provider_name,
                    )
                ],
            )
        messages_payload = payload.get("messages")
        if not isinstance(messages_payload, list):
            return ProviderSocialSentimentSourceResult(
                source=self.source,
                provider=self.provider_name,
                warnings=[
                    _malformed_stocktwits_payload_warning(
                        source=self.source,
                        provider=self.provider_name,
                    )
                ],
            )
        messages = messages_payload
        blocks: list[ProviderSocialSentimentSourceBlock] = []
        malformed_message_count = 0
        for message in messages[:limit]:
            parsed_message = _parse_stocktwits_message(message)
            if parsed_message is None:
                malformed_message_count += 1
                continue
            block = self._build_message_block(
                parsed_message,
                symbol=normalized_symbol,
                start_date=start_date,
                end_date=end_date,
            )
            if block is not None:
                blocks.append(block)
        warnings = (
            [
                _malformed_stocktwits_messages_warning(
                    malformed_message_count=malformed_message_count,
                    source=self.source,
                    provider=self.provider_name,
                )
            ]
            if malformed_message_count > 0
            else []
        )

        return ProviderSocialSentimentSourceResult(
            source=self.source,
            provider=self.provider_name,
            source_blocks=blocks,
            metrics=self._aggregate_metrics(blocks) if blocks else [],
            warnings=warnings,
        )

    def _build_message_block(
        self,
        message: _StockTwitsParsedMessage,
        *,
        symbol: str,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> ProviderSocialSentimentSourceBlock | None:
        as_of = message.as_of
        if not _within_bounds(as_of, start_date=start_date, end_date=end_date):
            return None
        user = _object_dict(message.payload.get("user"))
        username = _text(user.get("username")) or "unknown"
        sentiment = _stocktwits_sentiment(message.payload)
        message_id = _text(message.payload.get("id"))
        return ProviderSocialSentimentSourceBlock(
            source=self.source,
            provider=self.provider_name,
            title=f"@{username}",
            summary=_truncate(message.body, limit=280),
            url=(
                f"https://stocktwits.com/{username}/message/{message_id}"
                if message_id is not None
                else None
            ),
            as_of=as_of,
            symbols=[symbol],
            sentiment=sentiment,
            metrics=[
                ProviderSocialSentimentMetric(
                    name="message_count",
                    value=Decimal("1"),
                    unit="count",
                    source=self.source,
                    as_of=as_of,
                )
            ],
        )

    def _aggregate_metrics(
        self,
        blocks: list[ProviderSocialSentimentSourceBlock],
    ) -> list[ProviderSocialSentimentMetric]:
        total = len(blocks)
        bullish = sum(1 for block in blocks if block.sentiment == "positive")
        bearish = sum(1 for block in blocks if block.sentiment == "negative")
        unlabeled = total - bullish - bearish
        as_of = _latest_as_of(blocks)
        return [
            ProviderSocialSentimentMetric(
                "message_count", Decimal(total), "count", self.source, as_of
            ),
            ProviderSocialSentimentMetric(
                "bullish_count", Decimal(bullish), "count", self.source, as_of
            ),
            ProviderSocialSentimentMetric(
                "bearish_count", Decimal(bearish), "count", self.source, as_of
            ),
            ProviderSocialSentimentMetric(
                "unlabeled_count", Decimal(unlabeled), "count", self.source, as_of
            ),
            ProviderSocialSentimentMetric(
                "bullish_ratio", _ratio(bullish, total), None, self.source, as_of
            ),
            ProviderSocialSentimentMetric(
                "bearish_ratio", _ratio(bearish, total), None, self.source, as_of
            ),
        ]


def _request_json(
    url: str,
    *,
    params: dict[str, str | int],
    timeout: float,
    provider: str,
    source: SocialSentimentSource,
) -> dict[str, object]:
    headers = {"User-Agent": "signaldeck-backend/0.1", "Accept": "application/json"}
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params=params, headers=headers)
            _ = response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise SocialSentimentProviderTimeoutError(
            f"{provider} timed out while fetching {source} sentiment",
            details={"provider": provider, "source": source},
        ) from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 429:
            details = {"provider": provider, "source": source, "status": str(status_code)}
            retry_after = _retry_after_header_seconds(exc.response.headers.get("Retry-After"))
            if retry_after is not None:
                details["retryAfterSeconds"] = str(retry_after)
            raise SocialSentimentProviderRateLimitError(
                f"{provider} rate limited {source} sentiment",
                details=details,
            ) from exc
        if status_code >= 500:
            raise SocialSentimentProviderError(
                f"{provider} outage while fetching {source} sentiment",
                code="provider_unavailable",
                details={"provider": provider, "source": source, "status": str(status_code)},
            ) from exc
        raise SocialSentimentProviderError(
            f"{provider} failed while fetching {source} sentiment",
            details={"provider": provider, "source": source, "status": str(status_code)},
        ) from exc
    except httpx.HTTPError as exc:
        raise SocialSentimentProviderError(
            f"{provider} is unavailable for {source} sentiment",
            code="provider_unavailable",
            details={"provider": provider, "source": source},
        ) from exc

    payload = cast(object, response.json())
    if not isinstance(payload, dict):
        raise SocialSentimentProviderError(
            f"{provider} returned malformed {source} sentiment",
            details={"provider": provider, "source": source},
        )
    return cast(dict[str, object], payload)


def _request_text(
    url: str,
    *,
    params: dict[str, str | int],
    timeout: float,
    provider: str,
    source: SocialSentimentSource,
) -> str:
    headers = {"User-Agent": "signaldeck-backend/0.1", "Accept": "application/rss+xml"}
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params=params, headers=headers)
            _ = response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise SocialSentimentProviderTimeoutError(
            f"{provider} timed out while fetching {source} sentiment",
            details={"provider": provider, "source": source},
        ) from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 429:
            details = {"provider": provider, "source": source, "status": str(status_code)}
            retry_after = _retry_after_header_seconds(exc.response.headers.get("Retry-After"))
            if retry_after is not None:
                details["retryAfterSeconds"] = str(retry_after)
            raise SocialSentimentProviderRateLimitError(
                f"{provider} rate limited {source} sentiment",
                details=details,
            ) from exc
        if status_code >= 500:
            raise SocialSentimentProviderError(
                f"{provider} outage while fetching {source} sentiment",
                code="provider_unavailable",
                details={"provider": provider, "source": source, "status": str(status_code)},
            ) from exc
        raise SocialSentimentProviderError(
            f"{provider} failed while fetching {source} sentiment",
            details={"provider": provider, "source": source, "status": str(status_code)},
        ) from exc
    except httpx.HTTPError as exc:
        raise SocialSentimentProviderError(
            f"{provider} is unavailable for {source} sentiment",
            code="provider_unavailable",
            details={"provider": provider, "source": source},
        ) from exc
    return response.text


@dataclass(frozen=True, slots=True)
class _RedditTransport:
    json_fetcher: _JsonFetcher
    text_fetcher: _TextFetcher
    sleep: _Sleeper


@dataclass(frozen=True, slots=True)
class _RedditRequestConfig:
    subreddits: tuple[str, ...] = ("wallstreetbets", "stocks", "investing")
    retry_after_max_seconds: float = 2.0
    inter_request_delay_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class _StockTwitsTransport:
    json_fetcher: _JsonFetcher


@dataclass(frozen=True, slots=True)
class _StockTwitsParsedMessage:
    payload: dict[str, object]
    body: str
    as_of: datetime


def _parse_reddit_rss_blocks(
    payload: str,
    *,
    symbol: str,
    source: SocialSentimentSource,
    provider: str,
    limit: int,
) -> list[ProviderSocialSentimentSourceBlock]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise SocialSentimentProviderError(
            f"{provider} returned malformed {source} sentiment",
            details={"provider": provider, "source": source},
        ) from exc
    entries = [element for element in root.iter() if _local_name(element.tag) in {"entry", "item"}]
    return [
        _parse_reddit_rss_entry(
            entry,
            symbol=symbol,
            source=source,
            provider=provider,
        )
        for entry in entries[:limit]
    ]


def _parse_reddit_rss_entry(
    entry: ElementTree.Element,
    *,
    symbol: str,
    source: SocialSentimentSource,
    provider: str,
) -> ProviderSocialSentimentSourceBlock:
    summary = _child_text_by_local(entry, "content") or _child_text_by_local(entry, "description")
    published = _child_text_by_local(entry, "published") or _child_text_by_local(entry, "updated")
    pub_date = _child_text_by_local(entry, "pubDate")
    return ProviderSocialSentimentSourceBlock(
        source=source,
        provider=provider,
        title=_child_text_by_local(entry, "title"),
        summary=_truncate(_strip_html(summary), limit=280),
        url=_entry_link(entry),
        as_of=_entry_datetime(published=published, pub_date=pub_date),
        symbols=[symbol],
    )


def _element_text(element: ElementTree.Element, child_name: str) -> str | None:
    child = element.find(child_name)
    return _text(child.text if child is not None else None)


def _child_text_by_local(element: ElementTree.Element, child_name: str) -> str | None:
    for child in element:
        if _local_name(child.tag) == child_name:
            return _text(child.text)
    return None


def _entry_link(element: ElementTree.Element) -> str | None:
    for child in element:
        if _local_name(child.tag) != "link":
            continue
        href = _text(child.attrib.get("href"))
        return href or _text(child.text)
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str | None:
        normalized = " ".join(" ".join(self.parts).split())
        return normalized or None


def _strip_html(value: str | None) -> str | None:
    if value is None:
        return None
    parser = _HtmlTextExtractor()
    parser.feed(unescape(value))
    return parser.text()


def _entry_datetime(*, published: str | None, pub_date: str | None) -> datetime | None:
    return _iso_datetime(published) or _rss_datetime(pub_date)


def _retry_after_header_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(float(value)))
    except ValueError:
        parsed_datetime = _rss_datetime(value)
        if parsed_datetime is None:
            return None
        delta = parsed_datetime - datetime.now(tz=UTC)
        return max(0, int(delta.total_seconds()))


def _rss_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return to_utc(parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return None


def _warning_from_error(
    error: SocialSentimentProviderError,
    *,
    source: SocialSentimentSource,
    provider: str,
) -> ProviderSocialSentimentWarning:
    return ProviderSocialSentimentWarning(
        code=error.code,
        message=str(error),
        details={**error.details, "provider": provider, "source": source},
    )


def _error_with_subreddit(
    error: SocialSentimentProviderError,
    *,
    subreddit: str,
) -> SocialSentimentProviderError:
    details = {**error.details, "subreddit": subreddit}
    if isinstance(error, SocialSentimentProviderRateLimitError):
        return SocialSentimentProviderRateLimitError(str(error), details=details)
    if isinstance(error, SocialSentimentProviderTimeoutError):
        return SocialSentimentProviderTimeoutError(str(error), details=details)
    return SocialSentimentProviderError(str(error), code=error.code, details=details)


def _object_dict(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _object_list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, int):
        return str(value)
    return None


def _truncate(value: str | None, *, limit: int) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}…"


def _decimal_int(value: object) -> Decimal:
    if isinstance(value, bool):
        return Decimal("0")
    if isinstance(value, int | float):
        return Decimal(str(int(value)))
    return Decimal("0")


def _unix_datetime(value: object) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value), tz=UTC)
    return None


def _iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        iso_value = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
        return to_utc(datetime.fromisoformat(iso_value))
    except ValueError:
        return None


def _within_bounds(
    value: datetime | None,
    *,
    start_date: datetime | None,
    end_date: datetime | None,
) -> bool:
    if value is None:
        return True
    normalized = to_utc(value)
    if start_date is not None and normalized < to_utc(start_date):
        return False
    if end_date is not None and normalized > to_utc(end_date):
        return False
    return True


def _parse_stocktwits_message(value: object) -> _StockTwitsParsedMessage | None:
    if not isinstance(value, dict):
        return None
    payload = cast(dict[str, object], value)
    body = _text(payload.get("body"))
    as_of = _iso_datetime(_text(payload.get("created_at")))
    if body is None or as_of is None:
        return None
    return _StockTwitsParsedMessage(payload=payload, body=body, as_of=as_of)


def _malformed_stocktwits_payload_warning(
    *,
    source: SocialSentimentSource,
    provider: str,
) -> ProviderSocialSentimentWarning:
    return ProviderSocialSentimentWarning(
        code="provider_malformed_payload",
        message=f"{provider} returned malformed {source} sentiment payload",
        details={"provider": provider, "source": source, "field": "messages"},
    )


def _malformed_stocktwits_messages_warning(
    *,
    malformed_message_count: int,
    source: SocialSentimentSource,
    provider: str,
) -> ProviderSocialSentimentWarning:
    return ProviderSocialSentimentWarning(
        code="source_partial",
        message=f"{provider} skipped malformed {source} messages",
        details={
            "malformedMessageCount": str(malformed_message_count),
            "provider": provider,
            "source": source,
        },
    )


def _stocktwits_sentiment(
    message: dict[str, object],
) -> Literal["positive", "neutral", "negative", "mixed"] | None:
    entities = _object_dict(message.get("entities"))
    sentiment_payload = _object_dict(entities.get("sentiment"))
    basic = _text(sentiment_payload.get("basic"))
    if basic is None:
        return None
    if basic.lower() == "bullish":
        return "positive"
    if basic.lower() == "bearish":
        return "negative"
    return "neutral"


def _latest_as_of(blocks: Sequence[ProviderSocialSentimentSourceBlock]) -> datetime | None:
    timestamps = [to_utc(block.as_of) for block in blocks if block.as_of is not None]
    return max(timestamps) if timestamps else None


def _count_metrics(
    *,
    source: SocialSentimentSource,
    as_of: datetime | None,
    count: int,
) -> list[ProviderSocialSentimentMetric]:
    return [
        ProviderSocialSentimentMetric(
            name="mention_count",
            value=Decimal(count),
            unit="count",
            source=source,
            as_of=as_of,
        )
    ]


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))

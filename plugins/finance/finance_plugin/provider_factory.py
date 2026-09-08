"""Construct provider clients from explicit Finance deployment configuration."""

import os

from .config import FinanceSettings
from .providers.news_provider import (
    AlphaVantageNewsProvider,
    DeterministicNewsProvider,
    NewsProvider,
    YahooFinanceNewsProvider,
)
from .providers.quote_provider import (
    DeterministicQuoteProvider,
    QuoteProvider,
    YahooFinanceQuoteProvider,
)
from .providers.social_sentiment_provider import (
    RedditSocialSentimentAdapter,
    SocialSentimentSourceAdapter,
    StockTwitsSocialSentimentAdapter,
    _RedditRequestConfig,
)


def create_quote_provider(settings: FinanceSettings) -> QuoteProvider:
    if settings.quote_provider_backend == "deterministic":
        return DeterministicQuoteProvider()
    return YahooFinanceQuoteProvider(timeout=settings.quote_provider_timeout_seconds)


def create_news_providers(settings: FinanceSettings) -> tuple[NewsProvider, ...]:
    if settings.quote_provider_backend == "deterministic":
        return (DeterministicNewsProvider(),)
    providers: list[NewsProvider] = []
    for name in settings.news_provider_order:
        if name == "yahoo":
            providers.append(
                YahooFinanceNewsProvider(
                    timeout=settings.quote_provider_timeout_seconds,
                    global_queries=tuple(settings.global_news_queries),
                    global_lookback_days=settings.global_news_lookback_days,
                )
            )
        elif name == "alpha_vantage":
            # Credentials belong only to the selected plugin I/O client, never its descriptor.
            key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip() or None
            providers.append(
                AlphaVantageNewsProvider(
                    api_key=key, timeout=settings.quote_provider_timeout_seconds
                )
            )
        elif name == "deterministic":
            providers.append(DeterministicNewsProvider())
    return tuple(providers)


def create_social_sentiment_adapters(
    settings: FinanceSettings,
) -> tuple[SocialSentimentSourceAdapter, ...]:
    return (
        RedditSocialSentimentAdapter(
            timeout=settings.quote_provider_timeout_seconds,
            config=_RedditRequestConfig(
                subreddits=tuple(settings.reddit_subreddits),
                retry_after_max_seconds=settings.reddit_retry_after_max_seconds,
                inter_request_delay_seconds=settings.reddit_inter_request_delay_seconds,
            ),
        ),
        StockTwitsSocialSentimentAdapter(timeout=settings.quote_provider_timeout_seconds),
    )

"""Research projections of existing market, news and optional social providers."""

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from pydantic import Field

from .contracts import RuntimeToolContext
from .providers.social_sentiment_service import SocialSentimentService
from .research_collection import (
    ResearchCollectionOutput,
    ResearchScope,
    bounded_gaps,
    collection_cutoff,
    make_evidence,
    stable_id,
)
from .research_monitor_contracts import Coverage
from .research_report_validation import NY, day_end
from .services.market_data_service import MarketDataService, MarketIndicatorSelection


class ResearchMarketInput(ResearchScope):
    include_social: bool = False
    lookback_days: int = Field(default=7, ge=1, le=31)


def collect_market_evidence(
    payload: ResearchMarketInput,
    market: MarketDataService,
    social: SocialSentimentService,
    *,
    now: datetime | None = None,
) -> ResearchCollectionOutput:
    now = now or datetime.now(UTC)
    cutoff = collection_cutoff(payload, now)
    start = cutoff - timedelta(days=payload.lookback_days)
    evidence, gaps, coverage = [], [], []

    def record(source, items, warnings, *, complete=True):
        evidence.extend(items)
        gaps.extend(f"{source}: {message}" for message in warnings)
        coverage.append(
            Coverage(
                source_id=source,
                complete=complete and not warnings,
                observed_at=now,
                evidence_ids=[item.evidence_id for item in items],
                warning="; ".join(warnings) or None,
            )
        )

    try:
        result = market.get_ohlcv_snapshot(
            [payload.symbol], start_date=start, end_date=cutoff, row_limit=32
        )
        items = []
        warnings = [warning.message for warning in result.warnings]
        for series in result.series:
            if series.symbol != payload.symbol:
                continue
            if series.provider not in {"yahoo_finance", "deterministic_test"}:
                warnings.append("Market provider has no supported source URL mapping")
                continue
            url = f"https://finance.yahoo.com/quote/{quote(payload.symbol, safe='')}/history/"
            for row in series.rows:
                day = row.at.astimezone(NY).date()
                # Daily bars are labelled at session start, not when their close was known.
                # Date precision conservatively excludes an unfinished cutoff-day bar.
                if row.at < start or day_end(day) > cutoff:
                    continue
                for metric in ("open", "high", "low", "close", "volume"):
                    value = getattr(row, metric)
                    if value is None or (metric != "volume" and not series.currency):
                        continue
                    items.append(
                        make_evidence(
                            source_id=stable_id("market-", [series.provider, url]),
                            kind="observation",
                            source_type="market",
                            title=f"{payload.symbol} {metric}",
                            url=url,
                            publication_date=day,
                            retrieved_at=now,
                            period_end=day,
                            value=format(value, "f"),
                            unit="shares" if metric == "volume" else series.currency,
                            currency=None if metric == "volume" else series.currency,
                            metric=f"market.{metric}",
                            locator=f"{series.provider} daily bar {day}: {metric}",
                            symbol=payload.symbol,
                            verified=series.provider == "yahoo_finance",
                            uncertainty_reason=(
                                "Current historical endpoint; "
                                "revisions are not a point-in-time archive."
                            ),
                        )
                    )
        if not items:
            warnings.append("No completed daily bars available before cutoff")
        indicator_items, indicator_gaps = collect_indicators(market, payload, cutoff, items)
        items.extend(indicator_items)
        warnings.extend(indicator_gaps)
        record("market", items, warnings)
    except Exception:
        # Provider exceptions can contain request URLs or credentials; never echo them.
        record("market", [], ["Market collection failed"], complete=False)

    try:
        result = market.get_news_snapshot(
            symbols=[payload.symbol],
            scope="symbol",
            start_date=start,
            end_date=cutoff,
            item_limit=25,
        )
        warnings = [warning.message for warning in result.warnings]
        items = []
        for item in result.items:
            if not start <= item.published_at < cutoff or item.published_at > now:
                continue
            if not item.url:
                warnings.append("News item without an original URL excluded")
                continue
            items.append(
                make_evidence(
                    source_id=stable_id("news-", item.url),
                    kind="excerpt",
                    source_type="news",
                    title=item.title[:500],
                    url=item.url,
                    published_at=item.published_at,
                    retrieved_at=now,
                    text=(item.summary or item.title)[:12000],
                    locator=f"{item.source}: news headline/summary",
                    symbol=payload.symbol,
                    verified=True,
                    uncertainty_reason=(
                        "Provider headline/summary only; " "original article body was not read."
                    ),
                )
            )
        # Current search cannot establish that no historical news was published.
        if not items:
            warnings.append(
                "No news returned; current search is not an exhaustive historical archive"
            )
        record("news", items, warnings)
    except Exception:
        record("news", [], ["News collection failed"], complete=False)

    if payload.include_social:
        try:
            result = social.get_social_sentiment_snapshot(
                payload.symbol, start_date=start, end_date=cutoff, item_limit=25
            )
            warnings = [warning.message for warning in result.warnings]
            warnings.append(
                "Limited current social samples are not an exhaustive historical archive"
            )
            items = []
            for block in result.source_blocks:
                if not block.url or block.as_of is None or not start <= block.as_of < cutoff:
                    warnings.append("Social block with missing URL/time or outside cutoff excluded")
                    continue
                items.append(
                    make_evidence(
                        source_id=stable_id("social-", block.url),
                        kind="observation",
                        source_type="social",
                        title=(block.title or f"{block.source} discussion")[:500],
                        url=block.url,
                        published_at=block.as_of,
                        retrieved_at=now,
                        text=(block.summary or "")[:12000],
                        locator=f"{block.provider}/{block.source}: returned discussion sample",
                        symbol=payload.symbol,
                        verified=True,
                        uncertainty_reason=(
                            "Social discussion is a hypothesis lead, "
                            "not causal investment evidence."
                        ),
                    )
                )
                if block.metrics:
                    # Counts describe retrieval-time state, never the publication-time state.
                    metrics = ", ".join(f"{m.name}={m.value} {m.unit or ''}" for m in block.metrics)
                    warnings.append(
                        f"{block.source} sample counts observed at {now.isoformat()} "
                        f"(not cutoff): {metrics}"
                    )
            warnings.append(
                f"Returned {len(items)} eligible social samples from {','.join(result.sources)}"
            )
            record("social", items, warnings)
        except Exception:
            record("social", [], ["Optional social collection failed"], complete=False)
    return ResearchCollectionOutput(
        evidence=evidence, gaps=bounded_gaps(gaps), cutoff_at=cutoff, coverage=coverage
    )


def execute_market(arguments: dict, context: RuntimeToolContext):
    payload = ResearchMarketInput.model_validate(arguments)
    with context.session_factory() as session:
        market = MarketDataService(session, context.quote_provider, context.news_providers)
        return collect_market_evidence(
            payload, market, SocialSentimentService(context.social_sentiment_adapters)
        )


def collect_indicators(market, payload, cutoff, prices):
    """Project only completed-session indicators using existing bounded computation."""
    try:
        result = market.get_indicator_snapshot(
            payload.symbol,
            current_date=cutoff,
            start_date=cutoff - timedelta(days=90),
            end_date=cutoff,
            row_limit=30,
            indicators=[
                MarketIndicatorSelection(indicator="sma", window=20),
                MarketIndicatorSelection(indicator="rsi", window=14),
            ],
        )
        gaps = [warning.message for warning in result.warnings]
        rows = [row for row in result.rows if day_end(row.at.astimezone(NY).date()) <= cutoff]
        if not rows:
            return [], gaps + ["No completed indicator session available before cutoff"]
        latest = max(rows, key=lambda row: row.at)
        day = latest.at.astimezone(NY).date()
        price = next(
            (item for item in prices if item.metric == "market.close" and item.period_end == day),
            None,
        )
        if price is None:
            return [], gaps + ["Indicators have no matching dated price/currency source"]
        if price.locator is None or not price.locator.startswith(result.provider + " daily bar"):
            return [], gaps + ["Indicator provider differs from the dated price source"]
        values = {value.name: value for value in latest.values}
        items = []
        for name in ("sma_20", "rsi_14"):
            value = values.get(name)
            if value is None or value.value is None:
                reason = value.null_reason if value else "missing metric"
                gaps.append(f"{name} unavailable at {day}: {reason}")
                continue
            fields = price.model_dump(exclude={"evidence_id"})
            fields.update(
                title=f"{payload.symbol} {name}",
                metric=f"market.{name}",
                value=format(value.value, "f"),
                unit=price.unit if name == "sma_20" else "points",
                currency=price.currency if name == "sma_20" else None,
                locator=f"{result.provider} daily indicator {day}: {name}",
                text=(
                    "Computed from provider daily closes with a 90-day request window "
                    "and at most 30 returned bars; RSI is dimensionless points."
                ),
            )
            items.append(make_evidence(**fields))
        return items, gaps
    except Exception:
        return [], ["Technical indicator collection failed; daily prices remain available"]

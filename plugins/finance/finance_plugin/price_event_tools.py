"""Finance K-line event tool: symbol grants, one bounded provider read and result assembly."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from plugin_runtime.formatting import normalize_symbol
from plugin_runtime.serialization import model_wire_schema, project
from plugin_runtime.server import tool

from .contracts import RuntimeToolContext, RuntimeToolWarning
from .price_event_contracts import (
    WATCHLIST_LIMIT,
    PriceEventDetector,
    PriceEventSeries,
    PriceEventsLookupInput,
    PriceEventsLookupResult,
)
from .price_event_digest import render_digest
from .price_event_rules import detect_events
from .price_series import PriceSeries, complete_sessions, dividend_adjusted, summarize
from .providers.market_data_snapshots import MarketDataOhlcvSeries
from .research_report_validation import NY, day_end
from .services.market_data_service import MarketDataService

TOOL_NAME = "price_events_lookup"
TOOL_ID = "signaldeck/finance/" + TOOL_NAME
EVENT_LIMIT = 50
# About two years of calendar days, trimmed to the OHLCV tool's 500-bar ceiling.
HISTORY_DAYS = 740
HISTORY_ROWS = 500
# A watchlist scan reads up to 50 symbols one after another.
TIMEOUT_SECONDS = 120.0
DESCRIPTION = (
    "Detect rule-based daily K-line events for up to 5 granted US symbols, or for every "
    "granted symbol (at most 50) when symbols is omitted, in which case only the symbols with "
    "events are returned. Rules cover new closing highs "
    "or lows and approaches to them, drawdowns and rebounds, breakouts and failed breakouts, "
    "opening gaps, large one-session and multi-session moves, reversed large moves, gap fills, "
    "island reversals, moving-average, MACD, RSI and Bollinger signals, range contraction, "
    "inside bars, engulfing and pin-bar candles, volume spikes, streaks and relative strength. "
    "Only completed New York sessions count: a session is complete at 16:30 New York time on "
    "its date, and asOfDate (default now) bounds the scan. Rules read split- and "
    "dividend-adjusted prices scaled so the last completed session keeps its provider prices "
    "(priceBasis); each event also gives the provider rawClose, which older adjusted prices "
    "can differ from. Events come from the latest windowSessions sessions (default 20), newest "
    "first, at most 50 per symbol, each with its effective detector parameters. direction is "
    "the price direction of the event itself (a filled up-gap is a down event); set a "
    "detector's direction to keep one side. latestSession is the newest completed session "
    "among the scanned symbols; includeDigest adds a Chinese Markdown digest. Results describe "
    "past prices only, not forecasts, backtests or trading advice; disclose returned warnings."
)


def definition() -> dict:
    return {
        **tool(
            "signaldeck/finance",
            TOOL_NAME,
            {**model_wire_schema(PriceEventsLookupInput), "title": "识别K线事件"},
            model_wire_schema(PriceEventsLookupResult),
            DESCRIPTION,
            resources=("finance-market-data",),
        ),
        "timeoutSeconds": TIMEOUT_SECONDS,
    }


def execute(
    arguments: dict,
    invocation: dict,
    context: RuntimeToolContext,
    *,
    now: datetime | None = None,
) -> dict:
    payload = PriceEventsLookupInput.model_validate(arguments)
    granted = _granted_symbols(invocation)
    symbols = payload.symbols or _watchlist(granted)
    benchmark = payload.benchmark
    requested = list(dict.fromkeys([*symbols, *([benchmark] if benchmark else [])]))
    if any(symbol not in granted for symbol in requested):
        raise ValueError("finance_symbol_not_granted")
    as_of_date, cutoff = _cutoff(payload.as_of_date, now or datetime.now(UTC))
    with context.session_factory() as session:
        snapshot = MarketDataService(session, context.quote_provider).get_ohlcv_snapshot(
            requested,
            start_date=cutoff - timedelta(days=HISTORY_DAYS),
            end_date=cutoff,
            row_limit=HISTORY_ROWS,
        )
    provided = {series.symbol: series for series in snapshot.series}
    warnings = list(snapshot.warnings)
    benchmark_closes = None
    if benchmark in provided:
        sessions, _ = complete_sessions(provided[benchmark].rows, cutoff)
        adjusted = dividend_adjusted(sessions)
        # A scanned benchmark reports its own basis warning.
        if adjusted is None and sessions and benchmark not in symbols:
            warnings.append(_unadjusted_warning(benchmark))
        benchmark_closes = {session.day: session.close for session in adjusted or sessions}
    results = []
    for symbol in symbols:
        if symbol in provided:
            scanned = _scan(provided[symbol], payload, cutoff, benchmark_closes, warnings)
            if scanned is not None:
                results.append(scanned)
    # A watchlist scan reports only the symbols with events.
    reported = results if payload.symbols else [item for item in results if item.event_count]
    result = PriceEventsLookupResult(
        as_of_date=as_of_date,
        cutoff_at=cutoff,
        window_sessions=payload.window_sessions,
        scanned_symbols=symbols,
        latest_session=max((item.last_session for item in results), default=None),
        matched_count=sum(item.event_count for item in reported),
        series=reported,
        warnings=warnings,
    )
    if payload.include_digest:
        result.digest = render_digest(result, payload.detectors)
    return project(result.model_dump(mode="json", by_alias=True))


def _scan(
    provided: MarketDataOhlcvSeries,
    payload: PriceEventsLookupInput,
    cutoff: datetime,
    benchmark_closes: dict[date, Decimal] | None,
    warnings: list[RuntimeToolWarning],
) -> PriceEventSeries | None:
    """Evaluate one symbol's completed sessions, appending its warnings."""
    symbol = provided.symbol
    sessions, anomalies = complete_sessions(provided.rows, cutoff)
    if anomalies:
        warnings.append(_anomaly_warning(symbol, anomalies))
    if not sessions:
        warnings.append(
            _warning(
                "price_events_no_sessions",
                f"No completed sessions available for {symbol}",
                symbol=symbol,
            )
        )
        return None
    adjusted = dividend_adjusted(sessions)
    if adjusted is None:
        warnings.append(_unadjusted_warning(symbol))
    series = PriceSeries(
        adjusted or sessions, benchmark_closes, [session.close for session in sessions]
    )
    events, skipped = detect_events(series, payload.detectors, payload.window_sessions)
    warnings.extend(
        _skip_warning(symbol, detector, reason, count) for detector, reason, count in skipped
    )
    if len(events) > EVENT_LIMIT:
        warnings.append(
            _warning(
                "price_events_truncated",
                f"{len(events)} events found for {symbol}; the latest {EVENT_LIMIT} returned",
                symbol=symbol,
                limit=str(EVENT_LIMIT),
            )
        )
    return PriceEventSeries(
        symbol=symbol,
        provider=provided.provider,
        currency=provided.currency,
        price_basis="split_adjusted" if adjusted is None else "dividend_adjusted",
        first_session=sessions[0].day,
        last_session=sessions[-1].day,
        session_count=len(sessions),
        window_start=sessions[max(0, len(sessions) - payload.window_sessions)].day,
        state=summarize(series),
        event_count=len(events),
        events=events[:EVENT_LIMIT],
    )


def _granted_symbols(invocation: dict) -> list[str]:
    binding = invocation.get("resourceBindings", {}).get("finance-market-data", {})
    allowed = binding.get("allowedSymbols")
    if "finance-market-data" not in invocation.get("resourceGrants", []) or not isinstance(
        allowed, list
    ):
        raise ValueError("finance_resource_not_granted")
    return [symbol for symbol in dict.fromkeys(map(normalize_symbol, allowed)) if symbol]


def _watchlist(granted: list[str]) -> list[str]:
    if not granted:
        raise ValueError("price_events_no_granted_symbols")
    if len(granted) > WATCHLIST_LIMIT:
        raise ValueError("price_events_watchlist_too_large")
    return granted


def _cutoff(as_of_date: date | None, now: datetime) -> tuple[date, datetime]:
    today = now.astimezone(NY).date()
    if as_of_date is None:
        return today, now
    if as_of_date > today:
        raise ValueError("price_events_date_in_future")
    return as_of_date, min(day_end(as_of_date), now)


def _warning(code: str, message: str, **details: str) -> RuntimeToolWarning:
    return RuntimeToolWarning(code=code, message=message, details=details)


def _unadjusted_warning(symbol: str) -> RuntimeToolWarning:
    return _warning(
        "price_events_dividend_unadjusted",
        f"No dividend adjustment for {symbol}; its prices are split-adjusted only, "
        "so an ex-dividend drop can register as a down event",
        symbol=symbol,
    )


def _anomaly_warning(symbol: str, anomalies: list[tuple[date, str]]) -> RuntimeToolWarning:
    listed = ", ".join(f"{day.isoformat()} {reason}" for day, reason in anomalies[:10])
    return _warning(
        "price_events_data_anomaly",
        f"{len(anomalies)} provider bar issues for {symbol}; "
        f"events on these sessions may be unreliable: {listed}",
        symbol=symbol,
        count=str(len(anomalies)),
    )


def _skip_warning(
    symbol: str, detector: PriceEventDetector, reason: str, count: int
) -> RuntimeToolWarning:
    return _warning(
        "price_events_not_evaluated",
        f"{detector.label()} was not evaluated on {count} sessions for {symbol}: {reason}",
        symbol=symbol,
        detector=detector.type,
        reason=reason,
        sessions=str(count),
    )

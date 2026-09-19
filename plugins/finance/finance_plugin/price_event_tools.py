"""Finance K-line event tool: symbol grants, one bounded provider read and result assembly."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from plugin_runtime.serialization import model_wire_schema, project
from plugin_runtime.server import tool

from .contracts import RuntimeToolContext, RuntimeToolWarning
from .price_event_contracts import (
    PriceEventDetector,
    PriceEventSeries,
    PriceEventsLookupInput,
    PriceEventsLookupResult,
)
from .price_event_rules import detect_events
from .price_series import PriceSeries, complete_sessions, summarize
from .providers.market_data_snapshots import MarketDataOhlcvSeries
from .research_report_validation import NY, day_end
from .services.market_data_service import MarketDataService

TOOL_NAME = "price_events_lookup"
TOOL_ID = "signaldeck/finance/" + TOOL_NAME
EVENT_LIMIT = 50
# About two years of calendar days, trimmed to the OHLCV tool's 500-bar ceiling.
HISTORY_DAYS = 740
HISTORY_ROWS = 500
DESCRIPTION = (
    "Detect rule-based daily K-line events for up to 5 granted US symbols: new closing highs "
    "or lows, breakouts, opening gaps, large moves, gap fills, island reversals, moving-average, "
    "MACD, RSI and Bollinger signals, range contraction, inside bars, volume spikes, streaks and "
    "relative strength. Only completed New York sessions count: a session is complete at 16:30 "
    "New York time on its date, and asOfDate (default now) bounds the scan. Events come from "
    "the latest windowSessions sessions (default 20), newest first, at most 50 per symbol, each "
    "with its effective detector parameters. direction is the price direction of the event "
    "itself (a filled up-gap is a down event); set a detector's direction to keep one side. "
    "Results describe past prices only, not forecasts, backtests or trading advice; disclose "
    "returned warnings."
)


def definition() -> dict:
    return tool(
        "signaldeck/finance",
        TOOL_NAME,
        {**model_wire_schema(PriceEventsLookupInput), "title": "识别K线事件"},
        model_wire_schema(PriceEventsLookupResult),
        DESCRIPTION,
        resources=("finance-market-data",),
    )


def execute(
    arguments: dict,
    invocation: dict,
    context: RuntimeToolContext,
    *,
    now: datetime | None = None,
) -> dict:
    payload = PriceEventsLookupInput.model_validate(arguments)
    benchmark = payload.benchmark
    requested = list(dict.fromkeys([*payload.symbols, *([benchmark] if benchmark else [])]))
    _require_symbols(requested, invocation)
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
        benchmark_closes = {session.day: session.close for session in sessions}
    results = []
    for symbol in payload.symbols:
        if symbol in provided:
            scanned = _scan(provided[symbol], payload, cutoff, benchmark_closes, warnings)
            if scanned is not None:
                results.append(scanned)
    result = PriceEventsLookupResult(
        as_of_date=as_of_date,
        cutoff_at=cutoff,
        window_sessions=payload.window_sessions,
        matched_count=sum(item.event_count for item in results),
        series=results,
        warnings=warnings,
    )
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
    series = PriceSeries(sessions, benchmark_closes)
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
        first_session=sessions[0].day,
        last_session=sessions[-1].day,
        session_count=len(sessions),
        window_start=sessions[max(0, len(sessions) - payload.window_sessions)].day,
        state=summarize(series),
        event_count=len(events),
        events=events[:EVENT_LIMIT],
    )


def _require_symbols(requested: list[str], invocation: dict) -> None:
    binding = invocation.get("resourceBindings", {}).get("finance-market-data", {})
    allowed = binding.get("allowedSymbols")
    if "finance-market-data" not in invocation.get("resourceGrants", []) or not isinstance(
        allowed, list
    ):
        raise ValueError("finance_resource_not_granted")
    if any(symbol not in allowed for symbol in requested):
        raise ValueError("finance_symbol_not_granted")


def _cutoff(as_of_date: date | None, now: datetime) -> tuple[date, datetime]:
    today = now.astimezone(NY).date()
    if as_of_date is None:
        return today, now
    if as_of_date > today:
        raise ValueError("price_events_date_in_future")
    return as_of_date, min(day_end(as_of_date), now)


def _warning(code: str, message: str, **details: str) -> RuntimeToolWarning:
    return RuntimeToolWarning(code=code, message=message, details=details)


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

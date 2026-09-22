"""Finance's Yahoo provider maps yfinance frames and metadata onto Yahoo's own bar labels."""

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

for directory in ("runtime", "finance"):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / directory))

from finance_plugin.providers.quote_provider import QuoteProviderError  # noqa: E402
from finance_plugin.providers.yahoo_quote_provider import (  # noqa: E402
    YahooFinanceQuoteProvider,
)

NAN = float("nan")


class FakeTicker:
    def __init__(self, frame: pd.DataFrame, meta: dict[str, object]) -> None:
        self.frame = frame
        self.meta = meta
        self.history_calls: list[dict[str, object]] = []

    def history(self, **kwargs: object) -> pd.DataFrame:
        self.history_calls.append(kwargs)
        return self.frame

    def get_history_metadata(self) -> dict[str, object]:
        return self.meta


def _frame(days: list[str], rows: list[dict[str, float]]) -> pd.DataFrame:
    # yfinance labels daily, weekly and monthly bars at exchange-local midnight.
    index = pd.DatetimeIndex(pd.to_datetime(days)).tz_localize("America/New_York")
    return pd.DataFrame(rows, index=index)


def _meta(**extra: object) -> dict[str, object]:
    return {
        "currency": "USD",
        "exchangeTimezoneName": "America/New_York",
        "currentTradingPeriod": {
            "regular": {
                "start": pd.Timestamp("2026-09-21 09:30", tz="America/New_York"),
                "end": pd.Timestamp("2026-09-21 16:00", tz="America/New_York"),
            }
        },
        **extra,
    }


def _bar(close: float, *, adjusted: float | None = None, volume: float = 1000) -> dict:
    return {
        "Open": 100.5,
        "High": 101.25,
        "Low": 99.75,
        "Close": close,
        "Adj Close": close if adjusted is None else adjusted,
        "Volume": volume,
    }


def _provider(ticker: FakeTicker) -> YahooFinanceQuoteProvider:
    return YahooFinanceQuoteProvider(timeout=4.0, ticker_factory=lambda symbol: ticker)


def test_daily_bars_keep_yahoo_session_start_labels_within_the_window() -> None:
    ticker = FakeTicker(
        _frame(
            ["2026-01-15", "2026-07-30", "2026-07-31", "2026-08-03", "2026-08-04"],
            [
                _bar(100.0),
                _bar(101.0, adjusted=100.5, volume=NAN),
                _bar(NAN),
                _bar(103.0),
                _bar(104.0),
            ],
        ),
        _meta(),
    )
    start = datetime(2026, 1, 15, 10, tzinfo=UTC)
    # Midnight in New York after 2026-08-03: that session's bar is known, the next one is not.
    end = datetime(2026, 8, 4, 4, tzinfo=UTC)

    series = _provider(ticker).fetch_ohlcv(" aapl ", start_date=start, end_date=end, interval="1d")

    assert ticker.history_calls == [
        {"interval": "1d", "auto_adjust": False, "actions": False, "timeout": 4.0, "start": start}
    ]
    assert series.symbol == "AAPL"
    assert series.currency == "USD"
    assert series.provider == "yahoo_finance"
    assert [(row.at, row.close, row.volume, row.adjusted_close) for row in series.rows] == [
        (datetime(2026, 1, 15, 14, 30, tzinfo=UTC), Decimal("100.0"), 1000, Decimal("100.0")),
        (datetime(2026, 7, 30, 13, 30, tzinfo=UTC), Decimal("101.0"), None, Decimal("100.5")),
        (datetime(2026, 8, 3, 13, 30, tzinfo=UTC), Decimal("103.0"), 1000, Decimal("103.0")),
    ]
    assert (series.rows[0].open, series.rows[0].high, series.rows[0].low) == (
        Decimal("100.5"),
        Decimal("101.25"),
        Decimal("99.75"),
    )


def test_weekly_history_keeps_midnight_labels_and_requests_the_range() -> None:
    ticker = FakeTicker(_frame(["2026-09-07", "2026-09-14"], [_bar(100.0), _bar(NAN)]), _meta())

    series = _provider(ticker).fetch_history("MSFT", range_value="1y", interval="1wk")

    assert ticker.history_calls == [
        {"interval": "1wk", "auto_adjust": False, "actions": False, "timeout": 4.0, "period": "1y"}
    ]
    assert [(point.at, point.close) for point in series.points] == [
        (datetime(2026, 9, 7, 4, tzinfo=UTC), Decimal("100.0"))
    ]


def test_quote_reads_the_one_day_chart_metadata() -> None:
    ticker = FakeTicker(
        _frame(["2026-09-21"], [_bar(338.98)]),
        _meta(
            regularMarketPrice=338.98,
            previousClose=336.13,
            longName=" Apple Inc. ",
            regularMarketTime=pd.Timestamp("2026-09-21 16:00:01", tz="America/New_York"),
        ),
    )

    quote = _provider(ticker).fetch_quote("AAPL")

    assert ticker.history_calls[0]["period"] == "1d"
    assert (quote.symbol, quote.name, quote.price, quote.previous_close, quote.currency) == (
        "AAPL",
        "Apple Inc.",
        Decimal("338.98"),
        Decimal("336.13"),
        "USD",
    )
    assert quote.as_of == datetime(2026, 9, 21, 20, 0, 1, tzinfo=UTC)


def test_yfinance_failures_and_empty_frames_are_provider_errors() -> None:
    class FailingTicker(FakeTicker):
        def history(self, **kwargs: object) -> pd.DataFrame:
            raise RuntimeError("Too Many Requests")

    failing = FailingTicker(_frame([], []), _meta())
    with pytest.raises(QuoteProviderError, match="Quote request failed for AAPL"):
        _provider(failing).fetch_quote("AAPL")

    empty = FakeTicker(_frame(["2026-09-18"], [_bar(NAN)]), _meta())
    with pytest.raises(QuoteProviderError, match="OHLCV payload was empty for AAPL"):
        _provider(empty).fetch_ohlcv(
            "AAPL",
            start_date=datetime(2026, 9, 1, tzinfo=UTC),
            end_date=datetime(2026, 9, 21, tzinfo=UTC),
            interval="1d",
        )

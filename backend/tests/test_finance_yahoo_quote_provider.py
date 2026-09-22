"""Finance's Yahoo provider maps yfinance frames, tables and metadata onto Finance contracts."""

import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

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


def _ticker(**frames: object) -> YahooFinanceQuoteProvider:
    return YahooFinanceQuoteProvider(
        timeout=4.0, ticker_factory=lambda symbol: SimpleNamespace(**frames)
    )


def test_insider_rows_parse_the_type_and_a_single_price_within_bounds() -> None:
    frame = pd.DataFrame(
        [
            {
                "Insider": "A",
                "Position": "Director",
                "Text": "Sale at price 330.19 per share.",
                "Shares": 1438,
                "Value": 474813.0,
                "Start Date": pd.Timestamp("2026-09-15"),
            },
            {
                "Insider": "B",
                "Position": None,
                "Text": "Purchase at price 10.00 - 12.50 per share.",
                "Shares": 100,
                "Value": NAN,
                "Start Date": pd.Timestamp("2026-09-16"),
            },
            {
                "Insider": "C",
                "Position": "Officer",
                "Text": "",
                "Shares": 30104,
                "Value": NAN,
                "Start Date": pd.Timestamp("2026-09-17"),
            },
            {
                "Insider": None,
                "Position": "Officer",
                "Text": "Stock Gift",
                "Shares": 5,
                "Value": NAN,
                "Start Date": pd.Timestamp("2026-09-17"),
            },
            {
                "Insider": "D",
                "Position": "CFO",
                "Text": "Sale at price 1 per share.",
                "Shares": 1,
                "Value": 1.0,
                "Start Date": pd.Timestamp("2026-08-01"),
            },
        ]
    )

    data = _ticker(insider_transactions=frame).fetch_insider_transactions(
        "aapl",
        start_date=datetime(2026, 9, 1, tzinfo=UTC),
        end_date=datetime(2026, 9, 30, tzinfo=UTC),
        limit=5,
    )

    assert (data.symbol, data.provider) == ("AAPL", "yahoo_finance")
    assert [
        (row.insider_name, row.role, row.transaction_type, row.price, row.shares, row.value)
        for row in data.transactions
    ] == [
        ("C", "Officer", "Unspecified", None, Decimal("30104"), None),
        ("B", None, "Purchase", None, Decimal("100"), None),
        ("A", "Director", "Sale", Decimal("330.19"), Decimal("1438"), Decimal("474813.0")),
    ]
    assert data.transactions[-1].transaction_date == datetime(2026, 9, 15, tzinfo=UTC)
    assert all(row.filed_at is None for row in data.transactions)


def test_holders_convert_fractions_to_percent_and_skip_unnamed_rows() -> None:
    breakdown = pd.DataFrame(
        {"Value": [0.01648, 0.66341, 0.67453, 7760.0]},
        index=[
            "insidersPercentHeld",
            "institutionsPercentHeld",
            "institutionsFloatPercentHeld",
            "institutionsCount",
        ],
    )
    institutions = pd.DataFrame(
        [
            {
                "Date Reported": pd.Timestamp("2026-06-30"),
                "Holder": "Blackrock Inc.",
                "pctHeld": 0.0797,
                "Shares": 1162996939,
                "Value": 394232715159,
                "pctChange": 0.016,
            },
            {
                "Date Reported": pd.NaT,
                "Holder": "",
                "pctHeld": 0.01,
                "Shares": 1,
                "Value": 1,
                "pctChange": NAN,
            },
        ]
    )
    roster = pd.DataFrame(
        [
            {
                "Name": "COOK TIMOTHY D",
                "Position": "Chief Executive Officer",
                "Most Recent Transaction": "Sale",
                "Latest Transaction Date": pd.Timestamp("2026-04-02"),
                "Shares Owned Directly": 3280420,
                "Position Direct Date": pd.Timestamp("2026-04-02"),
            }
        ]
    )

    holders = _ticker(
        major_holders=breakdown,
        institutional_holders=institutions,
        mutualfund_holders=pd.DataFrame(),
        insider_roster_holders=roster,
    ).fetch_holders("AAPL")

    assert holders.breakdown.model_dump() == {
        "insiders_percent": Decimal("1.648"),
        "institutions_percent": Decimal("66.341"),
        "institutions_float_percent": Decimal("67.453"),
        "institution_count": 7760,
    }
    assert [
        (row.holder, row.report_date, row.percent_held, row.percent_change)
        for row in holders.institutions
    ] == [("Blackrock Inc.", date(2026, 6, 30), Decimal("7.97"), Decimal("1.6"))]
    assert holders.funds == []
    assert holders.insiders[0].latest_transaction_date == date(2026, 4, 2)
    assert (
        _ticker(
            major_holders=pd.DataFrame(),
            institutional_holders=pd.DataFrame(),
            mutualfund_holders=pd.DataFrame(),
            insider_roster_holders=pd.DataFrame(),
        )
        .fetch_holders("AAPL")
        .breakdown
        is None
    )


def test_estimates_join_periods_and_order_history_and_rating_changes() -> None:
    periods = pd.Index(["0q", "+1q"], name="period")
    eps = pd.DataFrame(
        {
            "avg": [1.97754, 2.9],
            "low": [1.93, 2.5],
            "high": [2.07, 3.4],
            "yearAgoEps": [1.85, 2.84],
            "numberOfAnalysts": [27, 21],
            "growth": [0.0689, 1.0],
            "currency": ["USD", "USD"],
        },
        index=periods,
    )
    trend = pd.DataFrame(
        {
            "current": [1.97754],
            "7daysAgo": [1.97754],
            "30daysAgo": [1.97656],
            "60daysAgo": [2.0179],
            "90daysAgo": [2.00836],
        },
        index=pd.Index(["0q"], name="period"),
    )
    revisions = pd.DataFrame(
        {"upLast7days": [1], "upLast30days": [7], "downLast30days": [14], "downLast7Days": [0]},
        index=pd.Index(["0y"], name="period"),
    )
    recommendations = pd.DataFrame(
        [
            {"period": "0m", "strongBuy": 6, "buy": 19, "hold": 13, "sell": 3, "strongSell": 3},
            {"period": "-1m", "strongBuy": NAN, "buy": 19, "hold": 14, "sell": 3, "strongSell": 2},
        ]
    )
    history = pd.DataFrame(
        {
            "epsActual": [1.85, 2.84],
            "epsEstimate": [1.76993, 2.6708],
            "epsDifference": [0.08, 0.17],
            "surprisePercent": [0.0452, 0.0634],
        },
        index=pd.DatetimeIndex(["2025-09-30", "2025-12-31"], name="quarter"),
    )
    ratings = pd.DataFrame(
        [
            {
                "Firm": "Early",
                "ToGrade": "Buy",
                "FromGrade": "",
                "Action": "init",
                "priceTargetAction": "Announces",
                "currentPriceTarget": 300.0,
                "priorPriceTarget": 0.0,
            },
            {
                "Firm": "Late",
                "ToGrade": "Hold",
                "FromGrade": "Buy",
                "Action": "down",
                "priceTargetAction": "Lowers",
                "currentPriceTarget": 310.0,
                "priorPriceTarget": 320.0,
            },
            {
                "Firm": "Same second",
                "ToGrade": "Buy",
                "FromGrade": "Buy",
                "Action": "main",
                "priceTargetAction": "Raises",
                "currentPriceTarget": 330.0,
                "priorPriceTarget": 325.0,
            },
        ],
        index=pd.DatetimeIndex(
            ["2026-09-01 10:00:00", "2026-09-18 11:45:30", "2026-09-18 11:45:30"], name="GradeDate"
        ),
    )

    estimates = _ticker(
        earnings_estimate=eps,
        revenue_estimate=pd.DataFrame(),
        eps_trend=trend,
        eps_revisions=revisions,
        analyst_price_targets={"current": 338.98, "high": 405.0, "low": None, "mean": 328.2},
        recommendations=recommendations,
        earnings_history=history,
        upgrades_downgrades=ratings,
    ).fetch_analyst_estimates("aapl")

    assert [period.period for period in estimates.periods] == ["0q", "+1q", "0y"]
    current = estimates.periods[0]
    assert (current.eps.average, current.eps.growth_percent, current.revenue) == (
        Decimal("1.97754"),
        Decimal("6.89"),
        None,
    )
    # The wire model writes str(Decimal), which must stay in plain notation.
    assert str(estimates.periods[1].eps.growth_percent) == "100"
    assert current.eps_trend.thirty_days_ago == Decimal("1.97656")
    assert estimates.periods[2].eps_revisions.down_last30_days == 14
    assert estimates.price_target.low is None and estimates.price_target.median is None
    assert [row.period for row in estimates.recommendations] == ["0m"]
    assert [(row.quarter_end, row.surprise_percent) for row in estimates.earnings_history] == [
        (date(2025, 12, 31), Decimal("6.34")),
        (date(2025, 9, 30), Decimal("4.52")),
    ]
    assert [
        (row.firm, row.at, row.from_grade, row.prior_price_target)
        for row in estimates.rating_changes
    ] == [
        ("Late", datetime(2026, 9, 18, 11, 45, 30, tzinfo=UTC), "Buy", Decimal("320.0")),
        ("Same second", datetime(2026, 9, 18, 11, 45, 30, tzinfo=UTC), "Buy", Decimal("325.0")),
        ("Early", datetime(2026, 9, 1, 10, tzinfo=UTC), None, None),
    ]

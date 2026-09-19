"""Finance K-line event rules, completed sessions and detector contracts."""

import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

for directory in ("runtime", "finance"):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / directory))

from finance_plugin.price_event_contracts import (  # noqa: E402
    PriceEventDetector,
    PriceEventsLookupInput,
)
from finance_plugin.price_event_rules import detect_events  # noqa: E402
from finance_plugin.price_series import (  # noqa: E402
    PriceSeries,
    Session,
    complete_sessions,
    summarize,
)

START = date(2026, 3, 2)


def trading_days(count: int) -> list[date]:
    days, day = [], START
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def closes(*values: float, volume: int | None = 1000) -> list[tuple]:
    """Bars that open at their close with a one-point range on each side."""
    return [(value, value + 1, value - 1, value, volume) for value in values]


def price_series(rows: list[tuple], benchmark: dict | None = None) -> PriceSeries:
    sessions = [
        Session(
            day,
            *(Decimal(str(value)) for value in row[:4]),
            None if row[4] is None else Decimal(row[4]),
        )
        for day, row in zip(trading_days(len(rows)), rows, strict=True)
    ]
    return PriceSeries(sessions, benchmark)


def detect(rows: list[tuple], detector: dict, *, benchmark: dict | None = None):
    series = price_series(rows, benchmark)
    return detect_events(series, [PriceEventDetector.model_validate(detector)], len(rows))


def described(events) -> list[tuple]:
    return [
        (
            trading_days(400).index(event.session),
            event.direction,
            {measure.name: str(measure.value) for measure in event.measures},
        )
        for event in events
    ]


def test_new_high_low_reports_the_base_length_and_ignores_ties() -> None:
    events, skipped = detect(
        closes(105, 100, 100, 100, 100, 106, 106, 94), {"type": "new_high_low", "lookback": 5}
    )
    assert described(events) == [
        (7, "down", {"breakPercent": "-6.0000", "sessionsSinceLevel": "3"}),
        (5, "up", {"breakPercent": "0.9524", "sessionsSinceLevel": "5"}),
    ]
    assert events[1].level == Decimal("105.0000")
    assert events[1].level_label == "highest_close_5"
    assert [(reason, count) for _, reason, count in skipped] == [("insufficient_history", 5)]


def test_breakout_requires_volume_confirmation_unless_disabled() -> None:
    history = closes(100, 100, 100)
    confirmed, _ = detect(
        [*history, (101, 103, 100, 102.5, 2000)], {"type": "breakout", "lookback": 3}
    )
    assert described(confirmed) == [
        (3, "up", {"breakPercent": "1.4851", "sessionsSinceLevel": "1", "volumeRatio": "2.0000"})
    ]
    assert confirmed[0].level_label == "highest_high_3"
    quiet, _ = detect([*history, (101, 103, 100, 102.5, 1200)], {"type": "breakout", "lookback": 3})
    assert quiet == []
    missing = [*history, (101, 103, 100, 102.5, None)]
    events, skipped = detect(missing, {"type": "breakout", "lookback": 3})
    assert events == [] and [(r, c) for _, r, c in skipped][-1] == ("missing_volume", 1)
    events, _ = detect(missing, {"type": "breakout", "lookback": 3, "volumeRatio": "0"})
    assert described(events) == [(3, "up", {"breakPercent": "1.4851", "sessionsSinceLevel": "1"})]


def test_gap_uses_the_prior_range_and_minimum_size() -> None:
    rows = [(100, 101, 99, 100, 1000), (103, 104, 102, 103.5, 1000), (97, 98, 96, 97, 1000)]
    events, _ = detect(rows, {"type": "gap"})
    assert described(events) == [
        (2, "down", {"gapPercent": "-4.9020"}),
        (1, "up", {"gapPercent": "1.9802"}),
    ]
    assert [event.level_label for event in events] == ["prior_low", "prior_high"]
    larger, _ = detect(rows, {"type": "gap", "minPercent": "2"})
    assert [event.direction for event in larger] == ["down"]
    upward, _ = detect(rows, {"type": "gap", "direction": "up"})
    assert [event.direction for event in upward] == ["up"]


def test_large_move_threshold_is_the_larger_of_percent_and_atr() -> None:
    calm = closes(*[100] * 15)
    events, _ = detect([*calm, (100, 106, 100, 105, 1000)], {"type": "large_move"})
    assert described(events) == [(15, "up", {"thresholdPercent": "4.0000", "moveAtr": "2.5000"})]
    small, _ = detect([*calm, (100, 104, 100, 103, 1000)], {"type": "large_move"})
    assert small == []
    wide = [(100, 103, 97, 100, 1000)] * 15
    volatile, _ = detect([*wide, (100, 106, 99, 105, 1000)], {"type": "large_move"})
    assert volatile == []
    crash, _ = detect([*wide, (100, 100, 85, 87, 1000)], {"type": "large_move"})
    assert described(crash) == [(15, "down", {"thresholdPercent": "12.0000", "moveAtr": "2.1667"})]
    _, skipped = detect(calm[:5], {"type": "large_move"})
    assert {reason for _, reason, _ in skipped} == {"insufficient_history"}


def test_large_move_adds_return_z_score_with_enough_history() -> None:
    history = closes(*[100 + (index % 2) for index in range(62)])
    events, _ = detect([*history, (101, 110, 101, 109, 1000)], {"type": "large_move"})
    assert described(events) == [
        (
            62,
            "up",
            {
                "thresholdPercent": "4.0000",
                "moveAtr": "4.0000",
                "returnZScore": "7.9552",
                "volumeRatio": "1.0000",
            },
        )
    ]


def test_gap_fill_reports_same_session_and_later_fills() -> None:
    base = closes(*[100] * 11)
    later = [
        *base,
        (103, 105, 102.5, 104, 1000),
        (104, 104, 102, 103, 1000),
        (102, 103, 100.5, 101, 1000),
    ]
    events, _ = detect(later, {"type": "gap_fill"})
    assert described(events) == [(13, "down", {"gapPercent": "1.9802", "sessionsToFill": "2"})]
    assert events[0].related_session == trading_days(14)[11]
    assert events[0].level == Decimal("101.0000")
    same = [*base, (97, 99.5, 96, 99, 1000)]
    events, _ = detect(same, {"type": "gap_fill"})
    assert described(events) == [(11, "up", {"gapPercent": "-2.0202", "sessionsToFill": "0"})]


def test_island_reversal_needs_gaps_on_both_sides() -> None:
    base = closes(*[100] * 11)
    island = [(104, 106, 103, 105, 1000), (105, 107, 104, 106, 1000)]
    top, _ = detect([*base, *island, (99, 100, 97, 98, 1000)], {"type": "island_reversal"})
    assert described(top) == [(13, "down", {"islandSessions": "2"})]
    assert top[0].level == Decimal("103.0000")
    assert top[0].related_session == trading_days(12)[11]
    overlap, _ = detect([*base, *island, (99, 103.5, 97, 98, 1000)], {"type": "island_reversal"})
    assert overlap == []
    bottom_island = [(96, 97, 94, 95, 1000)]
    bottom, _ = detect(
        [*base, *bottom_island, (99, 101, 98, 100, 1000)], {"type": "island_reversal"}
    )
    assert [(event.direction, event.level_label) for event in bottom] == [("up", "island_high")]


def test_moving_average_crosses() -> None:
    rows = closes(10, 10, 10, 9, 12)
    events, _ = detect(rows, {"type": "ma_cross", "fastWindow": 2, "slowWindow": 3})
    assert [(trading_days(5).index(event.session), event.direction) for event in events] == [
        (4, "up"),
        (3, "down"),
    ]
    assert events[0].level_label == "sma_3"
    price, _ = detect(closes(10, 10, 10, 11), {"type": "price_ma_cross", "window": 3})
    assert described(price) == [(3, "up", {"averageDistancePercent": "6.4516"})]


def test_macd_zero_line_cross_with_direction_filter() -> None:
    detector = {
        "type": "macd_cross",
        "fastWindow": 1,
        "slowWindow": 2,
        "signalWindow": 1,
        "reference": "zero",
    }
    events, _ = detect(closes(10, 10, 10, 9, 11), detector)
    assert [(trading_days(5).index(event.session), event.direction) for event in events] == [
        (4, "up"),
        (3, "down"),
    ]
    rising, _ = detect(closes(10, 10, 10, 9, 11), {**detector, "direction": "up"})
    assert [event.direction for event in rising] == ["up"]
    assert described(rising)[0][2]["macd"] == "0.5556"


def test_rsi_entering_overbought_fires_once() -> None:
    events, _ = detect(closes(10, 9, 10, 11, 12), {"type": "rsi_threshold", "window": 2})
    assert described(events) == [(3, "up", {"rsi": "75.0000"})]


def test_bollinger_break_and_squeeze() -> None:
    detector = {"type": "bollinger_break", "window": 3, "standardDeviations": "1"}
    events, _ = detect(closes(10, 10, 10, 13), detector)
    assert described(events) == [(3, "up", {"bandwidthPercent": "25.7130"})]
    assert events[0].level_label == "bollinger_upper_3_1"
    squeeze = {"type": "bollinger_squeeze", "window": 2, "standardDeviations": "1", "lookback": 3}
    events, skipped = detect(closes(10, 14, 10, 12, 11, 11.5), squeeze)
    assert [(trading_days(6).index(event.session), event.direction) for event in events] == [
        (5, "neutral"),
        (4, "neutral"),
    ]
    assert described(events)[1][2] == {
        "bandwidthPercent": "8.6957",
        "referenceBandwidthPercent": "18.1818",
    }
    assert sum(count for _, _, count in skipped) == 4


def test_range_contraction_and_inside_bar_are_strict() -> None:
    rows = [(100, 101, 99, 100, 1000), (100, 101.5, 98.5, 100, 1000), (100, 100.5, 100, 100, 1000)]
    events, _ = detect(rows, {"type": "range_contraction", "lookback": 3})
    assert described(events) == [(2, "neutral", {"rangePercent": "0.5000"})]
    tie = [*rows[:2], (100, 101, 99, 100, 1000)]
    assert detect(tie, {"type": "range_contraction", "lookback": 3})[0] == []
    inside, _ = detect(
        [(100, 105, 95, 100, 1000), (100, 104, 96, 101, 1000)], {"type": "inside_bar"}
    )
    assert [event.direction for event in inside] == ["neutral"]
    touching = [(100, 105, 95, 100, 1000), (100, 105, 96, 101, 1000)]
    assert detect(touching, {"type": "inside_bar"})[0] == []
    with pytest.raises(ValidationError, match="does not accept direction"):
        PriceEventDetector.model_validate({"type": "inside_bar", "direction": "up"})


def test_volume_spike_direction_follows_the_close() -> None:
    rows = [*closes(100, 100, 100), (100, 101, 97, 98, 3000)]
    events, _ = detect(rows, {"type": "volume_spike", "lookback": 3})
    assert described(events) == [
        (3, "down", {"volumeRatio": "3.0000", "volume": "3000", "averageVolume": "1000"})
    ]
    _, skipped = detect(
        [*closes(100, 100), (100, 101, 99, 100, None), *closes(100)],
        {"type": "volume_spike", "lookback": 3},
    )
    assert ("missing_volume", 1) in [(reason, count) for _, reason, count in skipped]


def test_streak_fires_when_the_run_reaches_its_length() -> None:
    events, _ = detect(closes(10, 11, 12, 13, 14, 13, 12, 11), {"type": "streak", "minLength": 3})
    assert described(events) == [
        (7, "down", {"streakLength": "3", "streakChangePercent": "-21.4286"}),
        (3, "up", {"streakLength": "3", "streakChangePercent": "30.0000"}),
    ]


def test_relative_strength_uses_aligned_benchmark_sessions() -> None:
    days = trading_days(4)
    benchmark = {day: Decimal("100") for day in days}
    detector = {"type": "relative_strength", "benchmark": "spy", "lookback": 3}
    events, _ = detect(closes(10, 10, 10, 12), detector, benchmark=benchmark)
    assert described(events) == [
        (
            3,
            "up",
            {
                "stockReturnPercent": "20.0000",
                "benchmarkReturnPercent": "0.0000",
                "excessReturnPercent": "20.0000",
            },
        )
    ]
    del benchmark[days[1]]
    events, skipped = detect(closes(10, 10, 10, 12), detector, benchmark=benchmark)
    assert events == [] and ("benchmark_gap", 1) in [(r, c) for _, r, c in skipped]


def test_completed_sessions_wait_for_the_new_york_settlement_time() -> None:
    def row(at: datetime, **prices: float) -> SimpleNamespace:
        values = {"open": 100, "high": 101, "low": 99, "close": 100, **prices}
        decimals = {key: Decimal(str(value)) for key, value in values.items()}
        return SimpleNamespace(at=at, volume=Decimal(1000), **decimals)

    friday = datetime(2026, 9, 18, 13, 30, tzinfo=UTC)
    rows = [
        row(friday - timedelta(days=3), open=102),
        row(friday - timedelta(days=2), close=0),
        row(friday - timedelta(days=1)),
        row(friday - timedelta(days=1) + timedelta(hours=3), close=100.5),
        row(friday),
    ]
    before, anomalies = complete_sessions(rows, datetime(2026, 9, 18, 20, 29, tzinfo=UTC))
    assert [session.day for session in before] == [date(2026, 9, 15), date(2026, 9, 17)]
    assert before[-1].close == Decimal("100.5")
    assert anomalies == [
        (date(2026, 9, 15), "price_outside_range"),
        (date(2026, 9, 16), "non_positive_price"),
        (date(2026, 9, 17), "duplicate_session"),
    ]
    after, _ = complete_sessions(rows, datetime(2026, 9, 18, 20, 30, tzinfo=UTC))
    assert after[-1].day == date(2026, 9, 18)


def test_latest_state_summarizes_ranges_trend_and_streak() -> None:
    rising = price_series(closes(*[100 + index for index in range(250)]))
    state = summarize(rising)
    assert state.ma_alignment == "bullish"
    assert state.streak == 249
    assert [
        (item.lookback, item.sessions_since_high, item.sessions_since_low) for item in state.ranges
    ] == [
        (20, 0, 19),
        (60, 0, 59),
        (250, 0, 249),
    ]
    assert state.ranges[0].distance_from_high_percent == Decimal("0.0000")
    assert state.ranges[0].distance_from_low_percent == Decimal("5.7576")
    short = summarize(price_series(closes(*[100] * 30)))
    assert [item.lookback for item in short.ranges] == [20]
    assert short.ma_alignment is None and short.sma50 is None and short.streak == 0


def test_detector_contract_fills_defaults_and_rejects_unsupported_parameters() -> None:
    breakout = PriceEventDetector.model_validate({"type": "breakout"})
    assert (breakout.lookback, breakout.volume_ratio) == (20, "1.5")
    assert breakout.label() == "breakout(lookback=20, volumeRatio=1.5)"
    invalid = [
        ({"type": "gap", "lookback": 5}, "does not accept lookback"),
        ({"type": "relative_strength"}, "requires benchmark"),
        ({"type": "ma_cross", "fastWindow": 50, "slowWindow": 20}, "fastWindow must be below"),
        ({"type": "rsi_threshold", "upper": "30", "lower": "70"}, "0 < lower < upper < 100"),
        (
            {"type": "large_move", "minPercent": "0", "atrMultiple": "0"},
            "minPercent or atrMultiple",
        ),
        ({"type": "volume_spike", "volumeRatio": "0"}, "must be above 0"),
        ({"type": "gap", "minPercent": "1e2"}, "plain decimal"),
    ]
    for arguments, message in invalid:
        with pytest.raises(ValidationError, match=message):
            PriceEventDetector.model_validate(arguments)


def test_lookup_input_normalizes_symbols_and_detectors() -> None:
    payload = PriceEventsLookupInput.model_validate(
        {
            "symbols": [" msft ", "MSFT", "aapl"],
            "detectors": [{"type": "gap"}, {"type": "gap", "minPercent": "1"}],
        }
    )
    assert payload.symbols == ["MSFT", "AAPL"]
    assert len(payload.detectors) == 1 and payload.window_sessions == 20
    assert payload.benchmark is None
    with pytest.raises(ValidationError, match="share one benchmark"):
        PriceEventsLookupInput.model_validate(
            {
                "symbols": ["MSFT"],
                "detectors": [
                    {"type": "relative_strength", "benchmark": "SPY"},
                    {"type": "relative_strength", "benchmark": "QQQ", "lookback": 20},
                ],
            }
        )

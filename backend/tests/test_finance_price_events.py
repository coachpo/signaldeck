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
    dividend_adjusted,
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


def test_min_base_sessions_keeps_breaks_of_older_extremes() -> None:
    rows = closes(105, 100, 100, 100, 100, 106, 107, 94)
    every, _ = detect(rows, {"type": "new_high_low", "lookback": 5})
    assert [trading_days(8).index(event.session) for event in every] == [7, 6, 5]
    based, _ = detect(rows, {"type": "new_high_low", "lookback": 5, "minBaseSessions": 3})
    assert described(based) == [
        (7, "down", {"breakPercent": "-6.0000", "sessionsSinceLevel": "3"}),
        (5, "up", {"breakPercent": "0.9524", "sessionsSinceLevel": "5"}),
    ]
    bar = (101, 103, 100, 102.5, 2000)
    detector = {"type": "breakout", "lookback": 3, "minBaseSessions": 2}
    assert detect([*closes(100, 100, 100), bar], detector)[0] == []
    events, skipped = detect([*closes(100, 100, 100), (*bar[:4], None)], detector)
    assert events == [] and "missing_volume" not in {reason for _, reason, _ in skipped}
    events, _ = detect([*closes(101, 100, 100), bar], detector)
    assert described(events) == [
        (3, "up", {"breakPercent": "0.4902", "sessionsSinceLevel": "3", "volumeRatio": "2.0000"})
    ]


def test_near_high_low_fires_when_entering_the_band() -> None:
    detector = {"type": "near_high_low", "lookback": 5}
    events, skipped = detect(closes(100, 100, 110, 100, 100, 100, 108.5, 109), detector)
    assert described(events) == [
        (6, "up", {"levelDistancePercent": "-1.3636", "sessionsSinceLevel": "4"})
    ]
    assert (events[0].level, events[0].level_label) == (Decimal("110.0000"), "highest_close_5")
    assert [(reason, count) for _, reason, count in skipped] == [("insufficient_history", 6)]
    low, _ = detect(closes(100, 90, 100, 100, 100, 100, 91.5), detector)
    assert described(low) == [
        (6, "down", {"levelDistancePercent": "1.6667", "sessionsSinceLevel": "5"})
    ]


def test_drawdown_and_rebound_fire_when_first_crossing_the_threshold() -> None:
    events, _ = detect(
        closes(100, 100, 100, 100, 100, 95, 89, 85, 100), {"type": "drawdown", "lookback": 5}
    )
    assert described(events) == [
        (8, "up", {"levelDistancePercent": "17.6471", "sessionsSinceLevel": "1"}),
        (6, "down", {"levelDistancePercent": "-11.0000", "sessionsSinceLevel": "2"}),
    ]
    assert [(event.level, event.level_label) for event in events] == [
        (Decimal("85.0000"), "lowest_close_5"),
        (Decimal("100.0000"), "highest_close_5"),
    ]


def test_failed_breakout_closes_back_inside_against_the_prior_close() -> None:
    detector = {"type": "failed_breakout", "lookback": 3}
    history = closes(100, 100, 100)
    events, _ = detect([*history, (100.5, 102, 99.5, 99.8, 1000)], detector)
    assert described(events) == [
        (
            3,
            "down",
            {
                "intradayBreakPercent": "0.9901",
                "levelDistancePercent": "-1.1881",
                "sessionsSinceLevel": "1",
            },
        )
    ]
    assert events[0].level_label == "highest_high_3"
    assert detect([*history, (100.5, 102, 99.5, 100.5, 1000)], detector)[0] == []
    events, _ = detect([*history, (99.5, 100.5, 98, 100.2, 1000)], detector)
    assert [(event.direction, event.level_label) for event in events] == [("up", "lowest_low_3")]


def test_window_move_fires_once_when_the_move_reaches_its_threshold() -> None:
    detector = {"type": "window_move", "window": 2, "minPercent": "5", "sigmaMultiple": "0"}
    events, _ = detect(closes(100, 100, 100, 103, 106, 107, 100, 94), detector)
    assert described(events) == [
        (6, "down", {"windowReturnPercent": "-5.6604", "thresholdPercent": "5.0000"}),
        (4, "up", {"windowReturnPercent": "6.0000", "thresholdPercent": "5.0000"}),
    ]
    assert events[1].related_session == trading_days(8)[2]
    assert events[1].level_label == "window_start_close"


def test_window_move_scales_the_threshold_by_prior_return_deviation() -> None:
    # Daily returns alternate +1% and -1%, so the deviation is exactly 1%.
    history = [Decimal(100)]
    for index in range(1, 62):
        history.append(history[-1] * (Decimal("1.01") if index % 2 else Decimal("0.99")))
    start = history[-1]
    moved = [start * Decimal(factor) for factor in ("1.01", "1.02", "1.04", "1.07")]
    detector = {"type": "window_move", "window": 4}
    events, skipped = detect(closes(*history, *moved), detector)
    assert described(events) == [
        (
            65,
            "up",
            {"windowReturnPercent": "7.0000", "thresholdPercent": "6.0000", "moveSigma": "3.5000"},
        )
    ]
    assert [(reason, count) for _, reason, count in skipped] == [("insufficient_history", 65)]


def test_spike_reversal_reports_the_first_close_back_beyond_the_pre_move_close() -> None:
    # Every candidate move in the ten-session reach needs its prior ATR.
    calm = closes(*[100] * 25)
    up = [(100, 106, 100, 105, 1000), (105, 105, 103, 104, 1000), (104, 104, 98, 99, 1000)]
    events, skipped = detect([*calm, *up, (99, 100, 97, 98, 1000)], {"type": "spike_reversal"})
    assert described(events) == [
        (
            27,
            "down",
            {"spikePercent": "5.0000", "sessionsToReverse": "2", "levelDistancePercent": "-1.0000"},
        )
    ]
    assert (events[0].level_label, events[0].related_session) == (
        "pre_move_close",
        trading_days(26)[25],
    )
    assert [(reason, count) for _, reason, count in skipped] == [("insufficient_history", 24)]
    down = [(100, 100, 94, 95, 1000), (95, 101.5, 95, 101, 1000)]
    events, _ = detect([*calm, *down], {"type": "spike_reversal"})
    assert described(events) == [
        (
            26,
            "up",
            {"spikePercent": "-5.0000", "sessionsToReverse": "1", "levelDistancePercent": "1.0000"},
        )
    ]


def test_engulfing_needs_the_opposite_prior_body_and_trend() -> None:
    detector = {"type": "engulfing", "trendSessions": 2}
    decline = [(110, 111, 109, 110, 1000), (105, 106, 104, 105, 1000)]
    bearish = (104, 105, 99, 100, 1000)
    events, _ = detect([*decline, bearish, (99, 106, 98, 105, 1000)], detector)
    assert described(events) == [
        (3, "up", {"bodyRatio": "1.5000", "trendChangePercent": "-9.0909"})
    ]
    advance = [(95, 96, 94, 95, 1000), (98, 99, 97, 98, 1000)]
    assert detect([*advance, bearish, (99, 106, 98, 105, 1000)], detector)[0] == []
    ignored, _ = detect(
        [*advance, bearish, (99, 106, 98, 105, 1000)], {"type": "engulfing", "trendSessions": 0}
    )
    assert described(ignored) == [(3, "up", {"bodyRatio": "1.5000"})]
    reversed_body, _ = detect([*decline, bearish, (100, 105, 99, 104, 1000)], detector)
    assert reversed_body == []
    rally = [(90, 91, 89, 90, 1000), (95, 96, 94, 95, 1000), (96, 101, 95, 100, 1000)]
    events, _ = detect([*rally, (101, 102, 94, 95, 1000)], detector)
    assert described(events) == [
        (3, "down", {"bodyRatio": "1.5000", "trendChangePercent": "11.1111"})
    ]


def test_pin_bar_needs_a_long_rejected_shadow_after_a_trend() -> None:
    detector = {"type": "pin_bar", "trendSessions": 2}
    decline = [(110, 111, 109, 110, 1000), (105, 106, 104, 105, 1000), (100, 101, 99, 100, 1000)]
    events, _ = detect([*decline, (99, 100, 94, 99.5, 1000)], detector)
    assert described(events) == [
        (
            3,
            "up",
            {"shadowRatio": "0.8333", "rangePercent": "6.0302", "trendChangePercent": "-9.0909"},
        )
    ]
    assert (events[0].level, events[0].level_label) == (Decimal("94.0000"), "session_low")
    assert detect([*decline, (99, 100, 97.5, 99.5, 1000)], detector)[0] == []
    rally = [(90, 91, 89, 90, 1000), (95, 96, 94, 95, 1000), (100, 101, 99, 100, 1000)]
    assert detect([*rally, (99, 100, 94, 99.5, 1000)], detector)[0] == []
    events, _ = detect([*rally, (101, 107, 100.5, 101.5, 1000)], detector)
    assert described(events) == [
        (
            3,
            "down",
            {"shadowRatio": "0.8462", "rangePercent": "6.4039", "trendChangePercent": "11.1111"},
        )
    ]
    assert events[0].level_label == "session_high"


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
                "sessionsSinceLevel": "1",
            },
        )
    ]
    based = {**detector, "minBaseSessions": 2}
    assert detect(closes(10, 10, 10, 12), based, benchmark=benchmark)[0] == []
    events, _ = detect(closes(11, 10, 10, 12), based, benchmark=benchmark)
    assert described(events)[0][2]["sessionsSinceLevel"] == "3"
    del benchmark[days[1]]
    events, skipped = detect(closes(10, 10, 10, 12), detector, benchmark=benchmark)
    assert events == [] and ("benchmark_gap", 1) in [(r, c) for _, r, c in skipped]


def test_completed_sessions_wait_for_the_new_york_settlement_time() -> None:
    def row(at: datetime, **prices: float) -> SimpleNamespace:
        values = {"open": 100, "high": 101, "low": 99, "close": 100, **prices}
        decimals = {key: Decimal(str(value)) for key, value in values.items()}
        return SimpleNamespace(at=at, volume=Decimal(1000), adjusted_close=None, **decimals)

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


def test_dividend_adjustment_keeps_the_last_session_and_one_factor_per_segment() -> None:
    days = trading_days(4)

    def session(day: date, close: str, adjusted: str | None) -> Session:
        price = Decimal(close)
        return Session(
            day, price, price + 1, price - 1, price, Decimal(1000), adjusted and Decimal(adjusted)
        )

    # Adjusted closes carry a later 1% dividend, a 2% one on days[2] and float noise.
    sessions = [
        session(days[0], "100", "97.0199901"),
        session(days[1], "100", "97.0200099"),
        session(days[2], "98", "97.02"),
        session(days[3], "98", "97.02"),
    ]
    adjusted = dividend_adjusted(sessions)
    assert adjusted is not None
    assert adjusted[0].close == adjusted[1].close == Decimal("98.00001")
    assert (adjusted[0].high, adjusted[0].low) == (Decimal("98.9800101"), Decimal("97.0200099"))
    assert adjusted[2:] == sessions[2:]
    assert dividend_adjusted([*sessions[:3], session(days[3], "98", None)]) is None
    assert dividend_adjusted([*sessions[:3], session(days[3], "98", "0")]) is None


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
    assert breakout.label() == "breakout(lookback=20, volumeRatio=1.5, minBaseSessions=1)"
    assert [
        PriceEventDetector.model_validate({"type": kind}).label()
        for kind in ("window_move", "spike_reversal", "near_high_low", "pin_bar")
    ] == [
        "window_move(window=5, minPercent=0, sigmaMultiple=3)",
        "spike_reversal(window=14, minPercent=4, atrMultiple=2, maxSessions=10)",
        "near_high_low(lookback=250, withinPercent=2)",
        "pin_bar(trendSessions=5)",
    ]
    invalid = [
        ({"type": "gap", "lookback": 5}, "does not accept lookback"),
        ({"type": "relative_strength"}, "requires benchmark"),
        ({"type": "ma_cross", "fastWindow": 50, "slowWindow": 20}, "fastWindow must be below"),
        ({"type": "rsi_threshold", "upper": "30", "lower": "70"}, "0 < lower < upper < 100"),
        (
            {"type": "large_move", "minPercent": "0", "atrMultiple": "0"},
            "minPercent or atrMultiple",
        ),
        (
            {"type": "spike_reversal", "minPercent": "0", "atrMultiple": "0"},
            "minPercent or atrMultiple",
        ),
        (
            {"type": "window_move", "minPercent": "0", "sigmaMultiple": "0"},
            "minPercent or sigmaMultiple",
        ),
        ({"type": "drawdown", "minPercent": "0"}, "drawdown minPercent must be above 0"),
        ({"type": "near_high_low", "withinPercent": "0"}, "withinPercent must be above 0"),
        (
            {"type": "new_high_low", "lookback": 10, "minBaseSessions": 11},
            "must not exceed lookback",
        ),
        ({"type": "engulfing", "minBaseSessions": 2}, "does not accept min_base_sessions"),
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

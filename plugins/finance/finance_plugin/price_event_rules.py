"""Closed daily K-line event rules evaluated on one security's completed sessions."""

from collections import Counter
from collections.abc import Callable, Sequence
from decimal import Decimal

from .price_event_contracts import PriceEvent, PriceEventDetector, PriceEventMeasure
from .price_series import FOUR_PLACES, PriceSeries, change_percent, last_index, quantize

# A rule returns the events at one session, or the reason it could not evaluate that session.
Outcome = list[PriceEvent] | str
INSUFFICIENT = "insufficient_history"
MISSING_VOLUME = "missing_volume"
BENCHMARK_GAP = "benchmark_gap"
ATR_MEASURE_WINDOW = 14
VOLUME_MEASURE_LOOKBACK = 20
Z_SCORE_LOOKBACK = 60


def detect_events(
    series: PriceSeries, detectors: Sequence[PriceEventDetector], window_sessions: int
) -> tuple[list[PriceEvent], list[tuple[PriceEventDetector, str, int]]]:
    """Evaluate every detector on the window sessions; newest events first."""
    start = max(0, len(series.days) - window_sessions)
    events: list[PriceEvent] = []
    skipped: list[tuple[PriceEventDetector, str, int]] = []
    for detector in detectors:
        rule = RULES[detector.type]
        reasons: Counter[str] = Counter()
        for index in range(start, len(series.days)):
            outcome = rule(series, detector, index)
            if isinstance(outcome, str):
                reasons[outcome] += 1
                continue
            events.extend(
                event for event in outcome if detector.direction in (None, event.direction)
            )
        skipped.extend((detector, reason, count) for reason, count in sorted(reasons.items()))
    # Stable sort keeps the requested detector order within one session.
    events.sort(key=lambda event: event.session, reverse=True)
    return events, skipped


def _measure(name: str, value: Decimal | int, unit: str) -> PriceEventMeasure:
    places = Decimal(1) if unit in {"sessions", "shares"} else FOUR_PLACES
    return PriceEventMeasure(name=name, value=quantize(Decimal(value), places), unit=unit)


def _event(
    series: PriceSeries,
    detector: PriceEventDetector,
    index: int,
    direction: str,
    *,
    level: Decimal | None = None,
    label: str | None = None,
    related: int | None = None,
    measures: Sequence[PriceEventMeasure | None] = (),
) -> list[PriceEvent]:
    close = series.closes[index]
    change = change_percent(close, series.closes[index - 1]) if index else None
    return [
        PriceEvent(
            detector=detector,
            direction=direction,
            session=series.days[index],
            close=quantize(close),
            change_percent=quantize(change) if change is not None else None,
            level=quantize(level) if level is not None else None,
            level_label=label,
            related_session=series.days[related] if related is not None else None,
            measures=[measure for measure in measures if measure is not None],
        )
    ]


def _beyond(value: Decimal, upper: Decimal, lower: Decimal) -> str | None:
    if value > upper:
        return "up"
    if value < lower:
        return "down"
    return None


def _crossing(
    current: Decimal, reference: Decimal, previous: Decimal, previous_reference: Decimal
) -> str | None:
    if current > reference and previous <= previous_reference:
        return "up"
    if current < reference and previous >= previous_reference:
        return "down"
    return None


def _new_high_low(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    lookback = detector.lookback
    if index < lookback:
        return INSUFFICIENT
    prior = series.closes[index - lookback : index]
    close = series.closes[index]
    direction = _beyond(close, max(prior), min(prior))
    if direction is None:
        return []
    level = max(prior) if direction == "up" else min(prior)
    label = "highest_close" if direction == "up" else "lowest_close"
    return _event(
        series,
        detector,
        index,
        direction,
        level=level,
        label=f"{label}_{lookback}",
        measures=[
            _measure("breakPercent", change_percent(close, level), "percent"),
            _measure("sessionsSinceLevel", lookback - last_index(prior, level), "sessions"),
        ],
    )


def _breakout(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    lookback = detector.lookback
    if index < lookback:
        return INSUFFICIENT
    highs = series.highs[index - lookback : index]
    lows = series.lows[index - lookback : index]
    close = series.closes[index]
    direction = _beyond(close, max(highs), min(lows))
    if direction is None:
        return []
    prior = highs if direction == "up" else lows
    level = max(highs) if direction == "up" else min(lows)
    volume = series.volume_ratio(index, lookback)
    required = Decimal(detector.volume_ratio)
    if required > 0:
        if volume is None:
            return MISSING_VOLUME
        if volume[0] < required:
            return []
    label = "highest_high" if direction == "up" else "lowest_low"
    return _event(
        series,
        detector,
        index,
        direction,
        level=level,
        label=f"{label}_{lookback}",
        measures=[
            _measure("breakPercent", change_percent(close, level), "percent"),
            _measure("sessionsSinceLevel", lookback - last_index(prior, level), "sessions"),
            _measure("volumeRatio", volume[0], "ratio") if volume else None,
        ],
    )


def _opening_gap(
    series: PriceSeries, index: int, minimum: Decimal
) -> tuple[str, Decimal, Decimal] | None:
    """Direction, size and pre-gap reference when the session opened beyond the prior range."""
    opening = series.opens[index]
    if opening > series.highs[index - 1]:
        reference = series.highs[index - 1]
    elif opening < series.lows[index - 1]:
        reference = series.lows[index - 1]
    else:
        return None
    percent = change_percent(opening, reference)
    if abs(percent) < minimum:
        return None
    return ("up" if percent > 0 else "down"), percent, reference


def _gap(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    if index < 1:
        return INSUFFICIENT
    gap = _opening_gap(series, index, Decimal(detector.min_percent))
    if gap is None:
        return []
    direction, percent, reference = gap
    atr = series.atr(ATR_MEASURE_WINDOW)[index - 1]
    return _event(
        series,
        detector,
        index,
        direction,
        level=reference,
        label="prior_high" if direction == "up" else "prior_low",
        measures=[
            _measure("gapPercent", percent, "percent"),
            _measure("gapAtr", abs(series.opens[index] - reference) / atr, "atr") if atr else None,
        ],
    )


def _large_move(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    if index < 1:
        return INSUFFICIENT
    atr = series.atr(detector.window)[index - 1]
    multiple = Decimal(detector.atr_multiple)
    if multiple > 0 and atr is None:
        return INSUFFICIENT
    previous, close = series.closes[index - 1], series.closes[index]
    change = change_percent(close, previous)
    threshold = Decimal(detector.min_percent)
    if atr is not None and multiple > 0:
        threshold = max(threshold, multiple * atr / previous * 100)
    if change == 0 or abs(change) < threshold:
        return []
    z_score = series.return_z_score(index, Z_SCORE_LOOKBACK)
    volume = series.volume_ratio(index, VOLUME_MEASURE_LOOKBACK)
    return _event(
        series,
        detector,
        index,
        "up" if change > 0 else "down",
        measures=[
            _measure("thresholdPercent", threshold, "percent"),
            _measure("moveAtr", abs(close - previous) / atr, "atr") if atr else None,
            _measure("returnZScore", z_score, "sigma") if z_score is not None else None,
            _measure("volumeRatio", volume[0], "ratio") if volume else None,
        ],
    )


def _fills(series: PriceSeries, index: int, direction: str, reference: Decimal) -> bool:
    if direction == "up":
        return series.lows[index] <= reference
    return series.highs[index] >= reference


def _gap_fill(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    limit = detector.max_sessions
    if index < limit + 1:
        return INSUFFICIENT
    minimum = Decimal(detector.min_percent)
    events: list[PriceEvent] = []
    for start in range(index - limit, index + 1):
        gap = _opening_gap(series, start, minimum)
        if gap is None:
            continue
        direction, percent, reference = gap
        if not _fills(series, index, direction, reference) or any(
            _fills(series, earlier, direction, reference) for earlier in range(start, index)
        ):
            continue
        # A filled up-gap is a move back down, and a filled down-gap a move back up.
        events += _event(
            series,
            detector,
            index,
            "down" if direction == "up" else "up",
            level=reference,
            label="prior_high" if direction == "up" else "prior_low",
            related=start,
            measures=[
                _measure("gapPercent", percent, "percent"),
                _measure("sessionsToFill", index - start, "sessions"),
            ],
        )
    return events


def _island_reversal(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    limit = detector.max_sessions
    if index < limit + 1:
        return INSUFFICIENT
    # The earliest qualifying start gives the complete island.
    for start in range(index - limit, index):
        low, high = min(series.lows[start:index]), max(series.highs[start:index])
        if low > series.highs[start - 1] and low > series.highs[index]:
            direction, level, label = "down", low, "island_low"
        elif high < series.lows[start - 1] and high < series.lows[index]:
            direction, level, label = "up", high, "island_high"
        else:
            continue
        return _event(
            series,
            detector,
            index,
            direction,
            level=level,
            label=label,
            related=start,
            measures=[_measure("islandSessions", index - start, "sessions")],
        )
    return []


def _ma_cross(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    fast = series.average(detector.average, detector.fast_window)
    slow = series.average(detector.average, detector.slow_window)
    if index < 1 or None in (fast[index], slow[index], fast[index - 1], slow[index - 1]):
        return INSUFFICIENT
    direction = _crossing(fast[index], slow[index], fast[index - 1], slow[index - 1])
    if direction is None:
        return []
    return _event(
        series,
        detector,
        index,
        direction,
        level=slow[index],
        label=f"{detector.average}_{detector.slow_window}",
        measures=[
            _measure("fastAverage", fast[index], "price"),
            _measure("slowAverage", slow[index], "price"),
        ],
    )


def _price_ma_cross(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    average = series.average(detector.average, detector.window)
    if index < 1 or None in (average[index], average[index - 1]):
        return INSUFFICIENT
    close = series.closes[index]
    direction = _crossing(close, average[index], series.closes[index - 1], average[index - 1])
    if direction is None:
        return []
    distance = change_percent(close, average[index])
    return _event(
        series,
        detector,
        index,
        direction,
        level=average[index],
        label=f"{detector.average}_{detector.window}",
        measures=[_measure("averageDistancePercent", distance, "percent")],
    )


def _macd_cross(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    if index < 1:
        return INSUFFICIENT
    macd = series.macd(detector.fast_window, detector.slow_window, detector.signal_window)
    line, signal, histogram = macd["line"], macd["signal"], macd["histogram"]
    if detector.reference == "zero":
        reference, previous_reference = Decimal(0), Decimal(0)
    else:
        reference, previous_reference = signal[index], signal[index - 1]
    if None in (line[index], line[index - 1], reference, previous_reference):
        return INSUFFICIENT
    direction = _crossing(line[index], reference, line[index - 1], previous_reference)
    if direction is None:
        return []
    return _event(
        series,
        detector,
        index,
        direction,
        measures=[
            _measure("macd", line[index], "price"),
            _measure("macdSignal", signal[index], "price") if signal[index] is not None else None,
            (
                _measure("macdHistogram", histogram[index], "price")
                if histogram[index] is not None
                else None
            ),
        ],
    )


def _rsi_threshold(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    rsi = series.rsi(detector.window)
    if index < 1 or None in (rsi[index], rsi[index - 1]):
        return INSUFFICIENT
    upper, lower = Decimal(detector.upper), Decimal(detector.lower)
    if rsi[index] >= upper > rsi[index - 1]:
        direction = "up"
    elif rsi[index] <= lower < rsi[index - 1]:
        direction = "down"
    else:
        return []
    return _event(
        series, detector, index, direction, measures=[_measure("rsi", rsi[index], "points")]
    )


def _bollinger_break(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    deviations = Decimal(detector.standard_deviations)
    bands = series.bollinger(detector.window, deviations)
    upper, lower = bands["upper"], bands["lower"]
    if index < 1 or None in (upper[index], upper[index - 1]):
        return INSUFFICIENT
    close, previous = series.closes[index], series.closes[index - 1]
    if close > upper[index] and previous <= upper[index - 1]:
        direction, level, band = "up", upper[index], "upper"
    elif close < lower[index] and previous >= lower[index - 1]:
        direction, level, band = "down", lower[index], "lower"
    else:
        return []
    token = format(deviations.normalize(), "f").replace(".", "_")
    width = series.bandwidth(detector.window, deviations)[index]
    return _event(
        series,
        detector,
        index,
        direction,
        level=level,
        label=f"bollinger_{band}_{detector.window}_{token}",
        measures=[_measure("bandwidthPercent", width, "percent") if width is not None else None],
    )


def _bollinger_squeeze(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    lookback = detector.lookback
    if index < lookback:
        return INSUFFICIENT
    width = series.bandwidth(detector.window, Decimal(detector.standard_deviations))
    history = width[index - lookback : index + 1]
    if None in history:
        return INSUFFICIENT
    reference, current = min(history[:-1]), history[-1]
    if current >= reference:
        return []
    return _event(
        series,
        detector,
        index,
        "neutral",
        measures=[
            _measure("bandwidthPercent", current, "percent"),
            _measure("referenceBandwidthPercent", reference, "percent"),
        ],
    )


def _range_percent(series: PriceSeries, index: int) -> Decimal:
    return (series.highs[index] - series.lows[index]) / series.closes[index] * 100


def _range_contraction(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    lookback = detector.lookback
    if index < lookback - 1:
        return INSUFFICIENT
    ranges = [series.highs[i] - series.lows[i] for i in range(index - lookback + 1, index + 1)]
    if ranges[-1] >= min(ranges[:-1]):
        return []
    return _event(
        series,
        detector,
        index,
        "neutral",
        measures=[_measure("rangePercent", _range_percent(series, index), "percent")],
    )


def _inside_bar(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    if index < 1:
        return INSUFFICIENT
    if not (
        series.highs[index] < series.highs[index - 1]
        and series.lows[index] > series.lows[index - 1]
    ):
        return []
    return _event(
        series,
        detector,
        index,
        "neutral",
        measures=[_measure("rangePercent", _range_percent(series, index), "percent")],
    )


def _volume_spike(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    lookback = detector.lookback
    if index < lookback:
        return INSUFFICIENT
    volume = series.volume_ratio(index, lookback)
    if volume is None:
        return MISSING_VOLUME
    ratio, average = volume
    if ratio < Decimal(detector.volume_ratio):
        return []
    change = series.closes[index] - series.closes[index - 1]
    direction = "up" if change > 0 else "down" if change < 0 else "neutral"
    return _event(
        series,
        detector,
        index,
        direction,
        measures=[
            _measure("volumeRatio", ratio, "ratio"),
            _measure("volume", series.volumes[index], "shares"),
            _measure("averageVolume", average, "shares"),
        ],
    )


def _streak(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    length = detector.min_length
    run = series.streaks()[index]
    if abs(run) != length:
        return []
    change = change_percent(series.closes[index], series.closes[index - length])
    return _event(
        series,
        detector,
        index,
        "up" if run > 0 else "down",
        measures=[
            _measure("streakLength", length, "sessions"),
            _measure("streakChangePercent", change, "percent"),
        ],
    )


def _relative_strength(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    lookback = detector.lookback
    if index < lookback:
        return INSUFFICIENT
    days = series.days[index - lookback : index + 1]
    benchmark = series.benchmark
    if benchmark is None or any(day not in benchmark for day in days):
        return BENCHMARK_GAP
    closes = series.closes[index - lookback : index + 1]
    ratios = [close / benchmark[day] for close, day in zip(closes, days, strict=True)]
    direction = _beyond(ratios[-1], max(ratios[:-1]), min(ratios[:-1]))
    if direction is None:
        return []
    stock = change_percent(closes[-1], closes[0])
    reference = change_percent(benchmark[days[-1]], benchmark[days[0]])
    return _event(
        series,
        detector,
        index,
        direction,
        measures=[
            _measure("stockReturnPercent", stock, "percent"),
            _measure("benchmarkReturnPercent", reference, "percent"),
            _measure("excessReturnPercent", stock - reference, "percent"),
        ],
    )


RULES: dict[str, Callable[[PriceSeries, PriceEventDetector, int], Outcome]] = {
    "new_high_low": _new_high_low,
    "breakout": _breakout,
    "gap": _gap,
    "large_move": _large_move,
    "gap_fill": _gap_fill,
    "island_reversal": _island_reversal,
    "ma_cross": _ma_cross,
    "price_ma_cross": _price_ma_cross,
    "macd_cross": _macd_cross,
    "rsi_threshold": _rsi_threshold,
    "bollinger_break": _bollinger_break,
    "bollinger_squeeze": _bollinger_squeeze,
    "range_contraction": _range_contraction,
    "inside_bar": _inside_bar,
    "volume_spike": _volume_spike,
    "streak": _streak,
    "relative_strength": _relative_strength,
}

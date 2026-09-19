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
            raw_close=quantize(series.raw_closes[index]),
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
    since = lookback - last_index(prior, level)
    if since < detector.min_base_sessions:
        return []
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
            _measure("sessionsSinceLevel", since, "sessions"),
        ],
    )


def _extreme_distance(
    series: PriceSeries, index: int, lookback: int, pick: Callable[[Sequence[Decimal]], Decimal]
) -> tuple[Decimal, Decimal, int]:
    """Close change from the picked prior closing extreme, that extreme and its age."""
    prior = series.closes[index - lookback : index]
    level = pick(prior)
    return change_percent(series.closes[index], level), level, lookback - last_index(prior, level)


def _near_high_low(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    lookback = detector.lookback
    if index <= lookback:
        return INSUFFICIENT
    within = Decimal(detector.within_percent)
    events: list[PriceEvent] = []
    for direction, pick, label, sign in (
        ("up", max, "highest_close", 1),
        ("down", min, "lowest_close", -1),
    ):
        distance, level, since = _extreme_distance(series, index, lookback, pick)
        previous = _extreme_distance(series, index - 1, lookback, pick)[0]
        # Entering the band from outside it; passing the extreme belongs to new_high_low.
        if -within <= sign * distance <= 0 and sign * previous < -within:
            events += _event(
                series,
                detector,
                index,
                direction,
                level=level,
                label=f"{label}_{lookback}",
                measures=[
                    _measure("levelDistancePercent", distance, "percent"),
                    _measure("sessionsSinceLevel", since, "sessions"),
                ],
            )
    return events


def _drawdown(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    lookback = detector.lookback
    if index <= lookback:
        return INSUFFICIENT
    minimum = Decimal(detector.min_percent)
    events: list[PriceEvent] = []
    for direction, pick, label, sign in (
        ("down", max, "highest_close", -1),
        ("up", min, "lowest_close", 1),
    ):
        distance, level, since = _extreme_distance(series, index, lookback, pick)
        previous = _extreme_distance(series, index - 1, lookback, pick)[0]
        if sign * distance >= minimum > sign * previous:
            events += _event(
                series,
                detector,
                index,
                direction,
                level=level,
                label=f"{label}_{lookback}",
                measures=[
                    _measure("levelDistancePercent", distance, "percent"),
                    _measure("sessionsSinceLevel", since, "sessions"),
                ],
            )
    return events


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
    since = lookback - last_index(prior, level)
    if since < detector.min_base_sessions:
        return []
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
            _measure("sessionsSinceLevel", since, "sessions"),
            _measure("volumeRatio", volume[0], "ratio") if volume else None,
        ],
    )


def _failed_breakout(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    lookback = detector.lookback
    if index < lookback:
        return INSUFFICIENT
    highs = series.highs[index - lookback : index]
    lows = series.lows[index - lookback : index]
    top, bottom = max(highs), min(lows)
    close, previous = series.closes[index], series.closes[index - 1]
    # A failed break up is a down event, and a failed break down an up event.
    if series.highs[index] > top and close < top and close < previous:
        direction, level, extreme, prior = "down", top, series.highs[index], highs
    elif series.lows[index] < bottom and close > bottom and close > previous:
        direction, level, extreme, prior = "up", bottom, series.lows[index], lows
    else:
        return []
    label = "highest_high" if direction == "down" else "lowest_low"
    return _event(
        series,
        detector,
        index,
        direction,
        level=level,
        label=f"{label}_{lookback}",
        measures=[
            _measure("intradayBreakPercent", change_percent(extreme, level), "percent"),
            _measure("levelDistancePercent", change_percent(close, level), "percent"),
            _measure("sessionsSinceLevel", lookback - last_index(prior, level), "sessions"),
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


def _move_threshold(
    series: PriceSeries, detector: PriceEventDetector, index: int
) -> Decimal | None:
    """Close change percent a large move needs at this session; None without ATR history."""
    threshold = Decimal(detector.min_percent)
    multiple = Decimal(detector.atr_multiple)
    if multiple > 0:
        atr = series.atr(detector.window)[index - 1]
        if atr is None:
            return None
        threshold = max(threshold, multiple * atr / series.closes[index - 1] * 100)
    return threshold


def _large_move(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    if index < 1:
        return INSUFFICIENT
    threshold = _move_threshold(series, detector, index)
    if threshold is None:
        return INSUFFICIENT
    atr = series.atr(detector.window)[index - 1]
    previous, close = series.closes[index - 1], series.closes[index]
    change = change_percent(close, previous)
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


def _window_change(
    series: PriceSeries, detector: PriceEventDetector, index: int
) -> tuple[str | None, Decimal, Decimal, Decimal | None] | None:
    """Side reached by the move over the window ending here, its size, threshold and scale."""
    start = index - detector.window
    change = change_percent(series.closes[index], series.closes[start])
    threshold = Decimal(detector.min_percent)
    multiple = Decimal(detector.sigma_multiple)
    scale = None
    if multiple > 0:
        # Deviation of the daily returns before the window, so the move cannot dilute it.
        moments = series.return_moments(start, Z_SCORE_LOOKBACK)
        if moments is None:
            return None
        scale = moments[1] * Decimal(detector.window).sqrt() * 100
        threshold = max(threshold, multiple * scale)
    side = None
    if change != 0 and abs(change) >= threshold:
        side = "up" if change > 0 else "down"
    return side, change, threshold, scale


def _window_move(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    if index <= detector.window:
        return INSUFFICIENT
    current = _window_change(series, detector, index)
    previous = _window_change(series, detector, index - 1)
    if current is None or previous is None:
        return INSUFFICIENT
    side, change, threshold, scale = current
    if side is None or side == previous[0]:
        return []
    start = index - detector.window
    return _event(
        series,
        detector,
        index,
        side,
        level=series.closes[start],
        label="window_start_close",
        related=start,
        measures=[
            _measure("windowReturnPercent", change, "percent"),
            _measure("thresholdPercent", threshold, "percent"),
            _measure("moveSigma", change / scale, "sigma") if scale else None,
        ],
    )


def _spike_reversal(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    limit = detector.max_sessions
    if index <= limit:
        return INSUFFICIENT
    close = series.closes[index]
    events: list[PriceEvent] = []
    for spike in range(index - limit, index):
        threshold = _move_threshold(series, detector, spike)
        if threshold is None:
            return INSUFFICIENT
        base = series.closes[spike - 1]
        move = change_percent(series.closes[spike], base)
        if move == 0 or abs(move) < threshold:
            continue
        sign = 1 if move > 0 else -1
        # Only the first close back beyond the pre-move close reverses the move.
        if sign * (close - base) >= 0 or any(
            sign * (series.closes[later] - base) < 0 for later in range(spike, index)
        ):
            continue
        events += _event(
            series,
            detector,
            index,
            "down" if sign > 0 else "up",
            level=base,
            label="pre_move_close",
            related=spike,
            measures=[
                _measure("spikePercent", move, "percent"),
                _measure("sessionsToReverse", index - spike, "sessions"),
                _measure("levelDistancePercent", change_percent(close, base), "percent"),
            ],
        )
    return events


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


def _prior_trend(series: PriceSeries, detector: PriceEventDetector, index: int) -> Decimal | None:
    """Close change into the session before the pattern completes; None when disabled."""
    sessions = detector.trend_sessions
    if not sessions:
        return None
    return change_percent(series.closes[index - 1], series.closes[index - 1 - sessions])


def _reverses(trend: Decimal | None, direction: str) -> bool:
    """A bullish pattern needs a prior decline and a bearish one a prior advance."""
    return trend is None or (trend < 0 if direction == "up" else trend > 0)


def _engulfing(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    if index <= detector.trend_sessions:
        return INSUFFICIENT
    prior_open, prior_close = series.opens[index - 1], series.closes[index - 1]
    opening, close = series.opens[index], series.closes[index]
    # The body covers the prior opposite body and is not just the same body reversed.
    if (opening, close) == (prior_close, prior_open):
        return []
    if opening <= prior_close < prior_open <= close:
        direction = "up"
    elif opening >= prior_close > prior_open >= close:
        direction = "down"
    else:
        return []
    trend = _prior_trend(series, detector, index)
    if not _reverses(trend, direction):
        return []
    return _event(
        series,
        detector,
        index,
        direction,
        measures=[
            _measure("bodyRatio", abs(close - opening) / abs(prior_close - prior_open), "ratio"),
            _measure("trendChangePercent", trend, "percent") if trend is not None else None,
        ],
    )


def _pin_bar(series: PriceSeries, detector: PriceEventDetector, index: int) -> Outcome:
    if index <= detector.trend_sessions:
        return INSUFFICIENT
    high, low = series.highs[index], series.lows[index]
    body = (series.opens[index], series.closes[index])
    span = high - low
    lower, upper = min(body) - low, high - max(body)
    # The rejected shadow takes at least two thirds of the session range.
    if span > 0 and 3 * lower >= 2 * span:
        direction, shadow, level, label = "up", lower, low, "session_low"
    elif span > 0 and 3 * upper >= 2 * span:
        direction, shadow, level, label = "down", upper, high, "session_high"
    else:
        return []
    trend = _prior_trend(series, detector, index)
    if not _reverses(trend, direction):
        return []
    return _event(
        series,
        detector,
        index,
        direction,
        level=level,
        label=label,
        measures=[
            _measure("shadowRatio", shadow / span, "ratio"),
            _measure("rangePercent", _range_percent(series, index), "percent"),
            _measure("trendChangePercent", trend, "percent") if trend is not None else None,
        ],
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
    prior = ratios[:-1]
    direction = _beyond(ratios[-1], max(prior), min(prior))
    if direction is None:
        return []
    since = lookback - last_index(prior, max(prior) if direction == "up" else min(prior))
    if since < detector.min_base_sessions:
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
            _measure("sessionsSinceLevel", since, "sessions"),
        ],
    )


RULES: dict[str, Callable[[PriceSeries, PriceEventDetector, int], Outcome]] = {
    "new_high_low": _new_high_low,
    "near_high_low": _near_high_low,
    "drawdown": _drawdown,
    "breakout": _breakout,
    "failed_breakout": _failed_breakout,
    "gap": _gap,
    "large_move": _large_move,
    "window_move": _window_move,
    "spike_reversal": _spike_reversal,
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
    "engulfing": _engulfing,
    "pin_bar": _pin_bar,
    "volume_spike": _volume_spike,
    "streak": _streak,
    "relative_strength": _relative_strength,
}

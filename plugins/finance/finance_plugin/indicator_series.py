"""Chronological daily indicator series; None marks points without enough history."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol


class PriceBar(Protocol):
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None


def sma(values: Sequence[Decimal], window: int) -> list[Decimal | None]:
    series: list[Decimal | None] = []
    for index in range(len(values)):
        if index + 1 < window:
            series.append(None)
            continue
        window_values = values[index + 1 - window : index + 1]
        series.append(sum(window_values, Decimal("0")) / Decimal(window))
    return series


def ema(values: Sequence[Decimal], window: int) -> list[Decimal | None]:
    series: list[Decimal | None] = [None] * len(values)
    if len(values) < window:
        return series
    multiplier = Decimal("2") / Decimal(window + 1)
    previous = sum(values[:window], Decimal("0")) / Decimal(window)
    series[window - 1] = previous
    for index in range(window, len(values)):
        previous = (values[index] - previous) * multiplier + previous
        series[index] = previous
    return series


def rsi(closes: Sequence[Decimal], window: int) -> list[Decimal | None]:
    series: list[Decimal | None] = [None] * len(closes)
    if len(closes) <= window:
        return series
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, Decimal("0")))
        losses.append(max(-change, Decimal("0")))
    average_gain = sum(gains[:window], Decimal("0")) / Decimal(window)
    average_loss = sum(losses[:window], Decimal("0")) / Decimal(window)
    series[window] = _rsi_value(average_gain, average_loss)
    for index in range(window + 1, len(closes)):
        average_gain = ((average_gain * Decimal(window - 1)) + gains[index - 1]) / Decimal(window)
        average_loss = ((average_loss * Decimal(window - 1)) + losses[index - 1]) / Decimal(window)
        series[index] = _rsi_value(average_gain, average_loss)
    return series


def macd(
    closes: Sequence[Decimal], fast_window: int, slow_window: int, signal_window: int
) -> dict[str, list[Decimal | None]]:
    fast_ema = ema(closes, fast_window)
    slow_ema = ema(closes, slow_window)
    line: list[Decimal | None] = []
    for fast_value, slow_value in zip(fast_ema, slow_ema, strict=True):
        line.append(
            fast_value - slow_value if fast_value is not None and slow_value is not None else None
        )
    signal: list[Decimal | None] = [None] * len(closes)
    macd_entries = [(index, value) for index, value in enumerate(line) if value is not None]
    if len(macd_entries) >= signal_window:
        multiplier = Decimal("2") / Decimal(signal_window + 1)
        previous = sum(
            (value for _, value in macd_entries[:signal_window]),
            Decimal("0"),
        ) / Decimal(signal_window)
        signal[macd_entries[signal_window - 1][0]] = previous
        for index, value in macd_entries[signal_window:]:
            previous = (value - previous) * multiplier + previous
            signal[index] = previous
    histogram = [
        (line_value - signal_value if line_value is not None and signal_value is not None else None)
        for line_value, signal_value in zip(line, signal, strict=True)
    ]
    return {"line": line, "signal": signal, "histogram": histogram}


def bollinger(
    closes: Sequence[Decimal], window: int, deviations: Decimal
) -> dict[str, list[Decimal | None]]:
    upper: list[Decimal | None] = []
    middle: list[Decimal | None] = []
    lower: list[Decimal | None] = []
    for index in range(len(closes)):
        if index + 1 < window:
            upper.append(None)
            middle.append(None)
            lower.append(None)
            continue
        window_values = closes[index + 1 - window : index + 1]
        average = sum(window_values, Decimal("0")) / Decimal(window)
        variance = sum(
            ((value - average) * (value - average) for value in window_values),
            Decimal("0"),
        ) / Decimal(window)
        width = variance.sqrt() * deviations
        upper.append(average + width)
        middle.append(average)
        lower.append(average - width)
    return {"upper": upper, "middle": middle, "lower": lower}


def atr(rows: Sequence[PriceBar], window: int) -> list[Decimal | None]:
    true_ranges: list[Decimal] = []
    for index, row in enumerate(rows):
        high_low = row.high - row.low
        if index == 0:
            true_ranges.append(high_low)
            continue
        previous_close = rows[index - 1].close
        true_ranges.append(
            max(
                high_low,
                abs(row.high - previous_close),
                abs(row.low - previous_close),
            )
        )
    series: list[Decimal | None] = [None] * len(rows)
    if len(true_ranges) < window:
        return series
    previous = sum(true_ranges[:window], Decimal("0")) / Decimal(window)
    series[window - 1] = previous
    for index in range(window, len(true_ranges)):
        previous = ((previous * Decimal(window - 1)) + true_ranges[index]) / Decimal(window)
        series[index] = previous
    return series


def vwma(rows: Sequence[PriceBar], window: int) -> list[Decimal | None]:
    series: list[Decimal | None] = []
    for index in range(len(rows)):
        if index + 1 < window:
            series.append(None)
            continue
        window_rows = rows[index + 1 - window : index + 1]
        volumes = [row.volume for row in window_rows]
        if any(volume is None for volume in volumes):
            series.append(None)
            continue
        total_volume = sum(Decimal(volume or 0) for volume in volumes)
        if total_volume <= 0:
            series.append(None)
            continue
        weighted_close = sum(
            (row.close * Decimal(row.volume or 0) for row in window_rows),
            Decimal("0"),
        )
        series.append(weighted_close / total_volume)
    return series


def _rsi_value(average_gain: Decimal, average_loss: Decimal) -> Decimal:
    if average_loss == 0:
        return Decimal("50") if average_gain == 0 else Decimal("100")
    relative_strength = average_gain / average_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + relative_strength))

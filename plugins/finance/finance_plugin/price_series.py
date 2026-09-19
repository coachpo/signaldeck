"""Completed New York daily sessions with memoized indicator series and latest state."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import pairwise
from typing import Protocol, TypeVar, cast

from . import indicator_series
from .price_event_contracts import PriceRange, PriceState
from .research_report_validation import NY

# Regular sessions close at 16:00; the extra half hour lets the provider settle the final bar.
SESSION_COMPLETE_AT = time(16, 30)
STATE_RANGES = (20, 60, 250)
FOUR_PLACES = Decimal("0.0001")
# Yahoo's float32 prices leave up to about 3e-7 of noise in adjusted/close ratios, while the
# smallest real dividend step is about 5e-5; ratios closer than this share one factor.
FACTOR_TOLERANCE = Decimal("0.00001")
_T = TypeVar("_T")


class ProviderBar(Protocol):
    at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    adjusted_close: Decimal | None


@dataclass(frozen=True, slots=True)
class Session:
    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    adjusted_close: Decimal | None = None


def complete_sessions(
    rows: Sequence[ProviderBar], cutoff: datetime
) -> tuple[list[Session], list[tuple[date, str]]]:
    """Keep sessions settled by the cutoff and report provider bars that look wrong."""
    latest: dict[date, ProviderBar] = {}
    anomalies: set[tuple[date, str]] = set()
    for row in sorted(rows, key=lambda item: item.at):
        day = row.at.astimezone(NY).date()
        if datetime.combine(day, SESSION_COMPLETE_AT, NY) > cutoff:
            continue
        if day in latest:
            anomalies.add((day, "duplicate_session"))
        latest[day] = row
    sessions: list[Session] = []
    for day, row in sorted(latest.items()):
        if min(row.open, row.high, row.low, row.close) <= 0:
            anomalies.add((day, "non_positive_price"))
            continue
        if not (row.low <= row.open <= row.high and row.low <= row.close <= row.high):
            anomalies.add((day, "price_outside_range"))
        if row.volume == 0:
            anomalies.add((day, "zero_volume"))
        sessions.append(
            Session(day, row.open, row.high, row.low, row.close, row.volume, row.adjusted_close)
        )
    return sessions, sorted(anomalies)


def dividend_adjusted(sessions: Sequence[Session]) -> list[Session] | None:
    """Scale prices by the provider's dividend adjustment so the last session keeps its prices.

    None when a session has no positive adjusted close.
    """
    if not sessions or any(
        session.adjusted_close is None or session.adjusted_close <= 0 for session in sessions
    ):
        return None
    last = sessions[-1]
    anchor = cast(Decimal, last.adjusted_close) / last.close
    adjusted: list[Session] = []
    factor: Decimal | None = None
    for session in reversed(sessions):
        ratio = cast(Decimal, session.adjusted_close) / session.close / anchor
        if factor is None or abs(ratio / factor - 1) >= FACTOR_TOLERANCE:
            factor = ratio
        adjusted.append(
            replace(
                session,
                open=session.open * factor,
                high=session.high * factor,
                low=session.low * factor,
                close=session.close * factor,
            )
        )
    adjusted.reverse()
    return adjusted


def quantize(value: Decimal, places: Decimal = FOUR_PLACES) -> Decimal:
    # Adding zero turns a rounded negative zero into zero.
    return value.quantize(places, rounding=ROUND_HALF_EVEN) + 0


def change_percent(current: Decimal, reference: Decimal) -> Decimal:
    return (current / reference - 1) * 100


def last_index(values: Sequence[Decimal], target: Decimal) -> int:
    return len(values) - 1 - list(reversed(values)).index(target)


class PriceSeries:
    def __init__(
        self,
        sessions: Sequence[Session],
        benchmark: Mapping[date, Decimal] | None = None,
        raw_closes: Sequence[Decimal] | None = None,
    ) -> None:
        """Rules read these session prices; raw_closes are the provider closes to report."""
        self.sessions = list(sessions)
        self.days = [session.day for session in self.sessions]
        self.opens = [session.open for session in self.sessions]
        self.highs = [session.high for session in self.sessions]
        self.lows = [session.low for session in self.sessions]
        self.closes = [session.close for session in self.sessions]
        self.raw_closes = self.closes if raw_closes is None else list(raw_closes)
        self.volumes = [session.volume for session in self.sessions]
        self.benchmark = benchmark
        self._memo: dict[tuple[object, ...], object] = {}

    def _cached(self, key: tuple[object, ...], compute: Callable[[], _T]) -> _T:
        if key not in self._memo:
            self._memo[key] = compute()
        return cast(_T, self._memo[key])

    def average(self, kind: str, window: int) -> list[Decimal | None]:
        compute = indicator_series.ema if kind == "ema" else indicator_series.sma
        return self._cached((kind, window), lambda: compute(self.closes, window))

    def atr(self, window: int) -> list[Decimal | None]:
        return self._cached(("atr", window), lambda: indicator_series.atr(self.sessions, window))

    def rsi(self, window: int) -> list[Decimal | None]:
        return self._cached(("rsi", window), lambda: indicator_series.rsi(self.closes, window))

    def macd(self, fast: int, slow: int, signal: int) -> dict[str, list[Decimal | None]]:
        return self._cached(
            ("macd", fast, slow, signal),
            lambda: indicator_series.macd(self.closes, fast, slow, signal),
        )

    def bollinger(self, window: int, deviations: Decimal) -> dict[str, list[Decimal | None]]:
        return self._cached(
            ("bollinger", window, deviations),
            lambda: indicator_series.bollinger(self.closes, window, deviations),
        )

    def bandwidth(self, window: int, deviations: Decimal) -> list[Decimal | None]:
        """Band width as a percent of the middle band."""
        bands = self.bollinger(window, deviations)
        return [
            (
                (upper - lower) / middle * 100
                if upper is not None and lower is not None and middle
                else None
            )
            for upper, middle, lower in zip(
                bands["upper"], bands["middle"], bands["lower"], strict=True
            )
        ]

    def volume_ratio(self, index: int, lookback: int) -> tuple[Decimal, Decimal] | None:
        """Session volume over the prior sessions' average, with that average."""
        if index < lookback:
            return None
        current = self.volumes[index]
        prior = self.volumes[index - lookback : index]
        if current is None or any(volume is None for volume in prior):
            return None
        average = sum(cast(list[Decimal], prior), Decimal(0)) / lookback
        if average <= 0:
            return None
        return current / average, average

    def streaks(self) -> list[int]:
        """Signed count of consecutive higher (positive) or lower (negative) closes."""

        def compute() -> list[int]:
            runs = [0]
            for previous, current in pairwise(self.closes):
                last = runs[-1]
                if current > previous:
                    runs.append(last + 1 if last > 0 else 1)
                elif current < previous:
                    runs.append(last - 1 if last < 0 else -1)
                else:
                    runs.append(0)
            return runs[: len(self.closes)]

        return self._cached(("streaks",), compute)

    def return_moments(self, end: int, lookback: int) -> tuple[Decimal, Decimal] | None:
        """Mean and population deviation of the daily returns into the lookback sessions to end."""
        if end < lookback:
            return None
        closes = self.closes
        returns = [closes[i] / closes[i - 1] - 1 for i in range(end - lookback + 1, end + 1)]
        mean = sum(returns, Decimal(0)) / lookback
        variance = sum(((value - mean) ** 2 for value in returns), Decimal(0)) / lookback
        return mean, variance.sqrt()

    def return_z_score(self, index: int, lookback: int) -> Decimal | None:
        """Session return against the mean and deviation of the prior daily returns."""
        moments = self.return_moments(index - 1, lookback)
        if moments is None or moments[1] == 0:
            return None
        mean, deviation = moments
        return (self.closes[index] / self.closes[index - 1] - 1 - mean) / deviation


def summarize(series: PriceSeries) -> PriceState:
    last = len(series.closes) - 1
    close = series.closes[last]
    ranges = []
    for lookback in STATE_RANGES:
        if len(series.closes) < lookback:
            continue
        window = series.closes[last - lookback + 1 :]
        highest, lowest = max(window), min(window)
        ranges.append(
            PriceRange(
                lookback=lookback,
                highest_close=quantize(highest),
                lowest_close=quantize(lowest),
                distance_from_high_percent=quantize(change_percent(close, highest)),
                distance_from_low_percent=quantize(change_percent(close, lowest)),
                sessions_since_high=lookback - 1 - last_index(window, highest),
                sessions_since_low=lookback - 1 - last_index(window, lowest),
            )
        )
    averages = [series.average("sma", window)[last] for window in (20, 50, 200)]
    alignment = None
    if all(value is not None for value in averages):
        ordered = [close, *cast(list[Decimal], averages)]
        if all(left > right for left, right in pairwise(ordered)):
            alignment = "bullish"
        elif all(left < right for left, right in pairwise(ordered)):
            alignment = "bearish"
        else:
            alignment = "mixed"
    atr, rsi = series.atr(14)[last], series.rsi(14)[last]
    volume = series.volume_ratio(last, 20)
    return PriceState(
        session=series.days[last],
        close=quantize(close),
        change_percent=(quantize(change_percent(close, series.closes[last - 1])) if last else None),
        ranges=ranges,
        sma20=_optional(averages[0]),
        sma50=_optional(averages[1]),
        sma200=_optional(averages[2]),
        ma_alignment=alignment,
        rsi14=_optional(rsi),
        atr14_percent=quantize(atr / close * 100) if atr is not None else None,
        volume_ratio20=quantize(volume[0]) if volume else None,
        streak=series.streaks()[last],
    )


def _optional(value: Decimal | None) -> Decimal | None:
    return None if value is None else quantize(value)

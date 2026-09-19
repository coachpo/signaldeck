"""Closed K-line event contracts: detector parameters, defaults and daily results."""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from plugin_runtime.common import CamelModel, ensure_timezone
from plugin_runtime.formatting import normalize_symbol
from pydantic import Field, field_validator, model_validator

from .contracts import RuntimeToolWarning
from .research_evidence import decimal_text

DetectorType = Literal[
    "new_high_low",
    "near_high_low",
    "drawdown",
    "breakout",
    "failed_breakout",
    "gap",
    "large_move",
    "window_move",
    "spike_reversal",
    "gap_fill",
    "island_reversal",
    "ma_cross",
    "price_ma_cross",
    "macd_cross",
    "rsi_threshold",
    "bollinger_break",
    "bollinger_squeeze",
    "range_contraction",
    "inside_bar",
    "engulfing",
    "pin_bar",
    "volume_spike",
    "streak",
    "relative_strength",
]

# Accepted parameters and their defaults; None marks a parameter the caller must supply.
DEFAULTS: dict[str, dict[str, object]] = {
    "new_high_low": {"lookback": 60, "min_base_sessions": 1},
    "near_high_low": {"lookback": 250, "within_percent": "2"},
    "drawdown": {"lookback": 60, "min_percent": "10"},
    "breakout": {"lookback": 20, "volume_ratio": "1.5", "min_base_sessions": 1},
    "failed_breakout": {"lookback": 20},
    "gap": {"min_percent": "1"},
    "large_move": {"min_percent": "4", "atr_multiple": "2", "window": 14},
    "window_move": {"window": 5, "sigma_multiple": "3", "min_percent": "0"},
    "spike_reversal": {"min_percent": "4", "atr_multiple": "2", "window": 14, "max_sessions": 10},
    "gap_fill": {"min_percent": "1", "max_sessions": 10},
    "island_reversal": {"max_sessions": 10},
    "ma_cross": {"fast_window": 50, "slow_window": 200, "average": "sma"},
    "price_ma_cross": {"window": 50, "average": "sma"},
    "macd_cross": {"fast_window": 12, "slow_window": 26, "signal_window": 9, "reference": "signal"},
    "rsi_threshold": {"window": 14, "upper": "70", "lower": "30"},
    "bollinger_break": {"window": 20, "standard_deviations": "2"},
    "bollinger_squeeze": {"window": 20, "standard_deviations": "2", "lookback": 120},
    "range_contraction": {"lookback": 7},
    "inside_bar": {},
    "engulfing": {"trend_sessions": 5},
    "pin_bar": {"trend_sessions": 5},
    "volume_spike": {"lookback": 20, "volume_ratio": "2"},
    "streak": {"min_length": 5},
    "relative_strength": {"benchmark": None, "lookback": 60, "min_base_sessions": 1},
}
NEUTRAL_DETECTORS = frozenset({"bollinger_squeeze", "range_contraction", "inside_bar"})

DETECTOR_GUIDE = (
    "Rule and optional parameters with defaults: new_high_low(lookback=60, minBaseSessions=1) "
    "close above the highest or below the lowest of the prior N closes; near_high_low("
    "lookback=250, withinPercent=2) first close within withinPercent below the highest (up) or "
    "above the lowest (down) of the prior N closes without passing it; drawdown(lookback=60, "
    "minPercent=10) first close at least minPercent below the highest (down) or above the "
    "lowest (up, a rebound) of the prior N closes; breakout(lookback=20, volumeRatio=1.5, "
    "minBaseSessions=1) close beyond the prior N highs or lows with volume at least ratio x "
    "their average, 0 disables the volume check; failed_breakout(lookback=20) high above the "
    "prior N highs (down) or low below the prior N lows (up) with the close back inside and "
    "against the prior close; gap(minPercent=1) open above the prior high or below the prior "
    "low; large_move(minPercent=4, atrMultiple=2, window=14) close change of at least "
    "max(minPercent, atrMultiple x prior ATR percent); window_move(window=5, sigmaMultiple=3, "
    "minPercent=0) first close whose change over N sessions reaches max(minPercent, "
    "sigmaMultiple x the daily return deviation of the 60 sessions before them x sqrt(N)); "
    "spike_reversal(minPercent=4, atrMultiple=2, window=14, maxSessions=10) first close back "
    "beyond the pre-move close within maxSessions of a large_move, an up move reversed is a "
    "down event; gap_fill(minPercent=1, maxSessions=10) first return to the pre-gap level; "
    "island_reversal(maxSessions=10) sessions isolated by a gap on each side; "
    "ma_cross(fastWindow=50, slowWindow=200, average=sma|ema); price_ma_cross(window=50, "
    "average=sma|ema); macd_cross(fastWindow=12, slowWindow=26, signalWindow=9, "
    "reference=signal|zero); rsi_threshold(window=14, upper=70, lower=30) RSI entering "
    "overbought (up) or oversold (down); bollinger_break(window=20, standardDeviations=2) first "
    "close outside a band; bollinger_squeeze(window=20, standardDeviations=2, lookback=120) band "
    "width below its prior N-session minimum; range_contraction(lookback=7) narrowest high-low "
    "range of N sessions; inside_bar; engulfing(trendSessions=5) real body engulfing the prior "
    "opposite body; pin_bar(trendSessions=5) lower (up, hammer) or upper (down, shooting star) "
    "shadow of at least two thirds of the range; engulfing and pin_bar need the prior close to "
    "be below (up) or above (down) the close trendSessions earlier, 0 disables this; "
    "volume_spike(lookback=20, volumeRatio=2); streak(minLength=5) consecutive higher or lower "
    "closes; relative_strength(benchmark required, lookback=60, minBaseSessions=1) "
    "close/benchmark ratio beyond its prior N-session range. minBaseSessions keeps only breaks "
    "of an extreme set at least that many sessions earlier; 1 keeps all. Decimal parameters "
    "are strings. bollinger_squeeze, range_contraction and inside_bar are neutral and do not "
    "accept direction."
)

# A watchlist scan covers every granted symbol, up to this many.
WATCHLIST_LIMIT = 50
DecimalText = Annotated[str, Field(min_length=1, max_length=20)]
Symbol = Annotated[str, Field(min_length=1, max_length=30)]


class PriceEventDetector(CamelModel):
    type: DetectorType = Field(description=DETECTOR_GUIDE)
    direction: Literal["up", "down"] | None = None
    lookback: int | None = Field(default=None, ge=2, le=250)
    window: int | None = Field(default=None, ge=2, le=250)
    fast_window: int | None = Field(default=None, ge=1, le=250)
    slow_window: int | None = Field(default=None, ge=2, le=250)
    signal_window: int | None = Field(default=None, ge=1, le=100)
    average: Literal["sma", "ema"] | None = None
    reference: Literal["signal", "zero"] | None = None
    standard_deviations: DecimalText | None = None
    min_percent: DecimalText | None = None
    atr_multiple: DecimalText | None = None
    volume_ratio: DecimalText | None = None
    upper: DecimalText | None = None
    lower: DecimalText | None = None
    min_length: int | None = Field(default=None, ge=2, le=30)
    max_sessions: int | None = Field(default=None, ge=1, le=30)
    min_base_sessions: int | None = Field(default=None, ge=1, le=250)
    sigma_multiple: DecimalText | None = None
    within_percent: DecimalText | None = None
    trend_sessions: int | None = Field(default=None, ge=0, le=60)
    benchmark: Symbol | None = None

    @field_validator(
        "standard_deviations",
        "min_percent",
        "atr_multiple",
        "volume_ratio",
        "upper",
        "lower",
        "sigma_multiple",
        "within_percent",
    )
    @classmethod
    def plain_decimal(cls, value: str | None) -> str | None:
        return None if value is None else decimal_text(value)

    @field_validator("benchmark")
    @classmethod
    def benchmark_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        symbol = normalize_symbol(value)
        if not symbol:
            raise ValueError("benchmark must not be empty")
        return symbol

    @model_validator(mode="after")
    def apply_defaults(self) -> Self:
        defaults = DEFAULTS[self.type]
        accepted = set(defaults) | (set() if self.type in NEUTRAL_DETECTORS else {"direction"})
        supplied = {
            name
            for name in type(self).model_fields
            if name != "type" and getattr(self, name) is not None
        }
        unsupported = sorted(supplied - accepted)
        if unsupported:
            raise ValueError(f"{self.type} does not accept {', '.join(unsupported)}")
        for name, value in defaults.items():
            if getattr(self, name) is None:
                if value is None:
                    raise ValueError(f"{self.type} requires {name}")
                setattr(self, name, value)
        self._check_ranges()
        return self

    def _check_ranges(self) -> None:
        def number(name: str) -> Decimal | None:
            value = getattr(self, name)
            return None if value is None else Decimal(value)

        deviations, minimum = number("standard_deviations"), number("min_percent")
        multiple, ratio = number("atr_multiple"), number("volume_ratio")
        sigmas, within = number("sigma_multiple"), number("within_percent")
        if deviations is not None and not 0 < deviations <= 10:
            raise ValueError("standardDeviations must be above 0 and at most 10")
        if minimum is not None and not 0 <= minimum <= 100:
            raise ValueError("minPercent must be between 0 and 100")
        if multiple is not None and not 0 <= multiple <= 20:
            raise ValueError("atrMultiple must be between 0 and 20")
        if ratio is not None and not 0 <= ratio <= 100:
            raise ValueError("volumeRatio must be between 0 and 100")
        if sigmas is not None and not 0 <= sigmas <= 20:
            raise ValueError("sigmaMultiple must be between 0 and 20")
        if within is not None and not 0 < within <= 100:
            raise ValueError("withinPercent must be above 0 and at most 100")
        if self.type == "volume_spike" and ratio == 0:
            raise ValueError("volume_spike volumeRatio must be above 0")
        if self.type in {"large_move", "spike_reversal"} and minimum == 0 and multiple == 0:
            raise ValueError(f"{self.type} needs minPercent or atrMultiple above 0")
        if self.type == "window_move" and minimum == 0 and sigmas == 0:
            raise ValueError("window_move needs minPercent or sigmaMultiple above 0")
        if self.type == "drawdown" and minimum == 0:
            raise ValueError("drawdown minPercent must be above 0")
        if (
            self.min_base_sessions is not None
            and self.lookback is not None
            and self.min_base_sessions > self.lookback
        ):
            raise ValueError("minBaseSessions must not exceed lookback")
        if self.type == "rsi_threshold":
            upper, lower = number("upper"), number("lower")
            if upper is None or lower is None or not 0 < lower < upper < 100:
                raise ValueError("rsi_threshold needs 0 < lower < upper < 100")
        if self.type in {"ma_cross", "macd_cross"} and (
            self.fast_window is None
            or self.slow_window is None
            or self.fast_window >= self.slow_window
        ):
            raise ValueError(f"{self.type} fastWindow must be below slowWindow")

    def label(self) -> str:
        values = self.model_dump(by_alias=True, exclude={"type"}, exclude_none=True)
        return f"{self.type}({', '.join(f'{key}={value}' for key, value in values.items())})"


class PriceEventsLookupInput(CamelModel):
    symbols: list[Symbol] | None = Field(
        default=None,
        min_length=1,
        max_length=5,
        description=(
            "Granted US symbols to scan. Omit to scan every granted symbol (at most 50) and "
            "return only the symbols with events."
        ),
    )
    as_of_date: date | None = None
    window_sessions: int = Field(default=20, ge=1, le=120)
    detectors: list[PriceEventDetector] = Field(
        min_length=1, max_length=20, description="Rules to evaluate; duplicates are ignored."
    )
    include_digest: bool = Field(
        default=False, description="Also return a Chinese Markdown digest of the scan."
    )

    @field_validator("symbols")
    @classmethod
    def unique_symbols(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        symbols: list[str] = []
        for value in values:
            symbol = normalize_symbol(value)
            if not symbol:
                raise ValueError("symbols must not contain empty values")
            if symbol not in symbols:
                symbols.append(symbol)
        return symbols

    @field_validator("detectors")
    @classmethod
    def unique_detectors(cls, values: list[PriceEventDetector]) -> list[PriceEventDetector]:
        unique: dict[str, PriceEventDetector] = {}
        for value in values:
            unique.setdefault(json.dumps(value.model_dump(mode="json"), sort_keys=True), value)
        return list(unique.values())

    @model_validator(mode="after")
    def one_benchmark(self) -> Self:
        if len({detector.benchmark for detector in self.detectors if detector.benchmark}) > 1:
            raise ValueError("relative_strength detectors must share one benchmark")
        return self

    @property
    def benchmark(self) -> str | None:
        return next((item.benchmark for item in self.detectors if item.benchmark), None)


MeasureName = Literal[
    "breakPercent",
    "sessionsSinceLevel",
    "levelDistancePercent",
    "intradayBreakPercent",
    "volumeRatio",
    "gapPercent",
    "gapAtr",
    "thresholdPercent",
    "moveAtr",
    "returnZScore",
    "windowReturnPercent",
    "moveSigma",
    "spikePercent",
    "sessionsToReverse",
    "sessionsToFill",
    "islandSessions",
    "fastAverage",
    "slowAverage",
    "averageDistancePercent",
    "macd",
    "macdSignal",
    "macdHistogram",
    "rsi",
    "bandwidthPercent",
    "referenceBandwidthPercent",
    "rangePercent",
    "bodyRatio",
    "shadowRatio",
    "trendChangePercent",
    "volume",
    "averageVolume",
    "streakLength",
    "streakChangePercent",
    "stockReturnPercent",
    "benchmarkReturnPercent",
    "excessReturnPercent",
]
MeasureUnit = Literal["percent", "price", "ratio", "sessions", "shares", "points", "atr", "sigma"]


class PriceEventMeasure(CamelModel):
    name: MeasureName
    value: Decimal
    unit: MeasureUnit


class PriceEvent(CamelModel):
    detector: PriceEventDetector
    direction: Literal["up", "down", "neutral"]
    session: date
    close: Decimal
    raw_close: Decimal
    change_percent: Decimal | None = None
    level: Decimal | None = None
    level_label: str | None = Field(default=None, min_length=1, max_length=80)
    related_session: date | None = None
    measures: list[PriceEventMeasure] = Field(default_factory=list, max_length=8)


class PriceRange(CamelModel):
    lookback: int
    highest_close: Decimal
    lowest_close: Decimal
    distance_from_high_percent: Decimal
    distance_from_low_percent: Decimal
    sessions_since_high: int
    sessions_since_low: int


class PriceState(CamelModel):
    session: date
    close: Decimal
    change_percent: Decimal | None = None
    ranges: list[PriceRange] = Field(default_factory=list, max_length=3)
    sma20: Decimal | None = None
    sma50: Decimal | None = None
    sma200: Decimal | None = None
    ma_alignment: Literal["bullish", "bearish", "mixed"] | None = None
    rsi14: Decimal | None = None
    atr14_percent: Decimal | None = None
    volume_ratio20: Decimal | None = None
    streak: int


class PriceEventSeries(CamelModel):
    symbol: str
    provider: str
    currency: str | None = None
    price_basis: Literal["dividend_adjusted", "split_adjusted"]
    first_session: date
    last_session: date
    session_count: int
    window_start: date
    state: PriceState
    event_count: int
    events: list[PriceEvent] = Field(max_length=50)


class PriceEventsLookupResult(CamelModel):
    as_of_date: date
    cutoff_at: datetime
    window_sessions: int
    scanned_symbols: list[str] = Field(max_length=WATCHLIST_LIMIT)
    latest_session: date | None = None
    matched_count: int
    series: list[PriceEventSeries] = Field(max_length=WATCHLIST_LIMIT)
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)
    digest: str | None = Field(default=None, min_length=1)

    @field_validator("cutoff_at")
    @classmethod
    def aware_cutoff(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

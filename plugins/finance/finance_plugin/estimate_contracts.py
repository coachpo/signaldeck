"""Public contract of the Finance analyst estimates tool: consensus, trends and ratings."""

from datetime import date, datetime
from decimal import Decimal

from plugin_runtime.common import CamelModel, ensure_timezone
from plugin_runtime.formatting import normalize_symbol
from pydantic import Field, field_validator

from .contracts import RuntimeToolWarning

RATING_CHANGE_LIMIT = 50


class AnalystEstimatesLookupInput(CamelModel):
    symbol: str = Field(min_length=1, max_length=32, description="One granted symbol.")
    rating_change_limit: int = Field(
        default=10,
        ge=0,
        le=RATING_CHANGE_LIMIT,
        description="Newest rating changes to return; 0 omits them.",
    )

    @field_validator("symbol")
    @classmethod
    def normalized(cls, value: str) -> str:
        return normalize_symbol(value)


class EstimateRange(CamelModel):
    average: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None
    year_ago: Decimal | None = None
    analyst_count: int | None = None
    growth_percent: Decimal | None = None
    currency: str | None = None


class EpsTrend(CamelModel):
    current: Decimal | None = None
    seven_days_ago: Decimal | None = None
    thirty_days_ago: Decimal | None = None
    sixty_days_ago: Decimal | None = None
    ninety_days_ago: Decimal | None = None


class EpsRevisions(CamelModel):
    up_last7_days: int | None = None
    up_last30_days: int | None = None
    down_last7_days: int | None = None
    down_last30_days: int | None = None


class EstimatePeriod(CamelModel):
    period: str = Field(description="0q current and +1q next fiscal quarter; 0y, +1y years.")
    eps: EstimateRange | None = None
    revenue: EstimateRange | None = None
    eps_trend: EpsTrend | None = None
    eps_revisions: EpsRevisions | None = None


class PriceTarget(CamelModel):
    current: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    mean: Decimal | None = None
    median: Decimal | None = None


class RecommendationCount(CamelModel):
    period: str = Field(description="0m is the current month, -1m the month before.")
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int


class EarningsSurprise(CamelModel):
    quarter_end: date
    eps_actual: Decimal | None = None
    eps_estimate: Decimal | None = None
    eps_difference: Decimal | None = None
    surprise_percent: Decimal | None = None


class RatingChange(CamelModel):
    at: datetime
    firm: str
    to_grade: str | None = None
    from_grade: str | None = None
    action: str | None = None
    price_target_action: str | None = None
    current_price_target: Decimal | None = None
    prior_price_target: Decimal | None = None

    @field_validator("at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class AnalystEstimatesSnapshot(CamelModel):
    """What a provider reports; rating changes are newest first and not yet limited."""

    symbol: str
    provider: str
    periods: list[EstimatePeriod] = Field(default_factory=list)
    price_target: PriceTarget | None = None
    recommendations: list[RecommendationCount] = Field(default_factory=list)
    earnings_history: list[EarningsSurprise] = Field(default_factory=list)
    rating_changes: list[RatingChange] = Field(default_factory=list)


class AnalystEstimatesLookupResult(AnalystEstimatesSnapshot):
    retrieved_at: datetime
    rating_change_count: int = Field(ge=0)
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("retrieved_at")
    @classmethod
    def retrieved_aware(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

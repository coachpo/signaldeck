"""Public contract of the Finance holders tool: ownership breakdown and largest holders."""

from datetime import date, datetime
from decimal import Decimal

from plugin_runtime.common import CamelModel, ensure_timezone
from plugin_runtime.formatting import normalize_symbol
from pydantic import Field, field_validator

from .contracts import RuntimeToolWarning


class HoldersLookupInput(CamelModel):
    symbol: str = Field(min_length=1, max_length=32, description="One granted symbol.")

    @field_validator("symbol")
    @classmethod
    def normalized(cls, value: str) -> str:
        return normalize_symbol(value)


class OwnershipBreakdown(CamelModel):
    insiders_percent: Decimal | None = None
    institutions_percent: Decimal | None = None
    institutions_float_percent: Decimal | None = None
    institution_count: int | None = None


class HolderPosition(CamelModel):
    holder: str
    report_date: date | None = None
    percent_held: Decimal | None = None
    shares: int | None = None
    value: Decimal | None = None
    percent_change: Decimal | None = None


class InsiderHolding(CamelModel):
    name: str
    position: str | None = None
    latest_transaction: str | None = None
    latest_transaction_date: date | None = None
    shares_owned_directly: int | None = None
    position_direct_date: date | None = None


class HoldersSnapshot(CamelModel):
    """What a provider reports; the tool adds the retrieval time and warnings."""

    symbol: str
    provider: str
    breakdown: OwnershipBreakdown | None = None
    institutions: list[HolderPosition] = Field(default_factory=list)
    funds: list[HolderPosition] = Field(default_factory=list)
    insiders: list[InsiderHolding] = Field(default_factory=list)


class HoldersLookupResult(HoldersSnapshot):
    retrieved_at: datetime
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("retrieved_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

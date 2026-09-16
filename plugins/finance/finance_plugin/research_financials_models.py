"""SEC financial facts retain original concepts, periods and accession revisions."""

from datetime import date, datetime
from typing import Literal

from plugin_runtime.common import CamelModel
from pydantic import Field


class FinancialFact(CamelModel):
    evidence_id: str
    source_id: str
    metric: str
    taxonomy: str
    tag: str
    alias_tags: list[str] = Field(default_factory=list)
    value: str
    unit: str
    currency: str | None = None
    period_start: date | None = None
    period_end: date
    period_type: Literal[
        "instant", "quarterly", "year_to_date", "annual", "other", "trailing_twelve_months"
    ]
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    accession: str
    form: str
    filed_at: date
    accepted_at: datetime | None = None
    locator: str
    excerpt: str
    supersedes_evidence_ids: list[str] = Field(default_factory=list, max_length=300)
    selected: bool = True
    operand_evidence_ids: list[str] = Field(default_factory=list, max_length=300)
    formula_version: str | None = None
    rounding: str | None = None


class FinancialGap(CamelModel):
    period_end: date | None = None
    code: str
    metric: str
    message: str


# Aliases are deliberately narrow: semantic changes cannot be resolved by tag priority.
METRIC_TAGS = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss",),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capital_expenditures": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "productive_asset_expenditures": ("PaymentsToAcquireProductiveAssets",),
    "long_term_debt": ("LongTermDebt",),
    "current_debt": ("DebtCurrent",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "short_term_debt": ("ShortTermBorrowings",),
    "long_term_debt_current": ("LongTermDebtCurrent",),
    "long_term_debt_noncurrent": ("LongTermDebtNoncurrent",),
    "shares_outstanding": ("CommonStockSharesOutstanding",),
    "weighted_average_shares": ("WeightedAverageNumberOfSharesOutstandingBasic",),
    "diluted_weighted_average_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
}


class FinancialCoverage(CamelModel):
    source_id: str
    complete: bool
    observed_at: datetime
    evidence_ids: list[str] = Field(default_factory=list, max_length=300)
    warning: str | None = None

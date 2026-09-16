"""Bounded FRED vintage evidence without confusing observation and availability dates."""

import os
from datetime import UTC, date, datetime, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

from plugin_runtime.common import CamelModel
from pydantic import Field, field_validator

from .research_documents import SourceCoverage, cutoff, digest
from .research_documents_evidence import ResearchEvidence
from .runtime_macro_rates_client import HttpxMacroRatesJsonClient
from .runtime_macro_rates_providers import FredMacroRatesProvider
from .types import DigitalOracleMacroRatesProviderQuery, DigitalOracleProviderError

DEFAULT_SERIES = ["CPIAUCSL", "CPILFESL", "A191RL1Q225SBEA", "UNRATE", "FEDFUNDS"]


class MacroEvidenceQuery(CamelModel):
    series_ids: list[str] = Field(default_factory=lambda: list(DEFAULT_SERIES), max_length=5)
    as_of_date: date | None = None
    cutoff_at: datetime | None = None

    @field_validator("cutoff_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("cutoffAt requires timezone")
        return value

    @field_validator("series_ids")
    @classmethod
    def valid_series(cls, value):
        if any(
            not series or len(series) > 80 or not series.replace("_", "").isalnum()
            for series in value
        ):
            raise ValueError("Expected explicit FRED series identifiers")
        return list(dict.fromkeys(value))


class MacroEvidenceResult(CamelModel):
    cutoff_at: datetime
    available_by_date: date
    evidence: list[ResearchEvidence] = Field(default_factory=list, max_length=300)
    coverage: list[SourceCoverage] = Field(default_factory=list, max_length=30)
    gaps: list[str] = Field(default_factory=list, max_length=100)


class BudgetClient(HttpxMacroRatesJsonClient):
    def __init__(self):
        self.deadline = monotonic() + 15

    def get_json(self, url, *, params, timeout, provider, api_key=None):
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise DigitalOracleProviderError(
                "FRED request budget exhausted", code="provider_timeout"
            )
        return super().get_json(
            url, params=params, timeout=min(timeout, remaining), provider=provider, api_key=api_key
        )


def lookup_macro_evidence(arguments: dict) -> MacroEvidenceResult:
    query = MacroEvidenceQuery.model_validate(arguments)
    bound = cutoff(query, datetime.now(UTC))
    # The previous NY calendar date is the newest complete day at any instant,
    # including exactly midnight. A date vintage is not an intraday publication time.
    vintage = bound.astimezone(ZoneInfo("America/New_York")).date() - timedelta(days=1)
    result = MacroEvidenceResult(cutoff_at=bound, available_by_date=vintage)
    key = os.environ.get("FRED_API_KEY")
    if not key:
        result.gaps.append("fred_api_key_not_configured")
    elif not query.series_ids:
        result.gaps.append("macro_selection_empty")
    else:
        provider = FredMacroRatesProvider(http_client=BudgetClient())
        for series_id in query.series_ids:
            try:
                data = provider.lookup_macro_rates(
                    DigitalOracleMacroRatesProviderQuery(
                        source="fred",
                        query=None,
                        families=("macro_indicators",),
                        series_ids=(series_id,),
                        countries=("US",),
                        start_date=None,
                        end_date=vintage,
                        as_of_date=vintage,
                        item_limit=10,
                        timeout_seconds=15,
                        fred_api_key=key,
                    )
                )
                result.gaps.extend(f"{series_id}:{warning.code}" for warning in data.warnings)
                if not data.series:
                    result.gaps.append(f"{series_id}:no_observations")
                for row in data.series[:10]:
                    value = format(row.value, "f")
                    result.evidence.append(
                        ResearchEvidence(
                            evidence_id=digest(
                                f"fred:{series_id}:{row.date}:{value}:{row.unit}".encode()
                            ),
                            source_id=f"fred:{series_id}",
                            kind="observation",
                            title=row.label,
                            url=row.source_url,
                            retrieved_at=datetime.now(UTC),
                            available_by_date=vintage,
                            period_end=row.date,
                            value=value,
                            unit=row.unit,
                            metric=series_id,
                            verified=True,
                            source_type="official",
                            locator=(
                                f"FRED series {series_id}; observation {row.date}; "
                                f"vintage {vintage}"
                            ),
                            uncertainty_reason=(
                                "FRED real-time vintage establishes availability by this "
                                "complete date; original publication timestamp is unknown."
                            ),
                        )
                    )
            except (DigitalOracleProviderError, ValueError):
                result.gaps.append(f"{series_id}:fred_vintage_unavailable")
    result.coverage = [
        SourceCoverage(
            source_id="macro",
            complete=bool(result.evidence) and not result.gaps,
            observed_at=datetime.now(UTC),
            evidence_ids=[e.evidence_id for e in result.evidence],
            warning="; ".join(result.gaps) or None,
        )
    ]
    return result

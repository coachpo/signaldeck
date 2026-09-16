"""Closed contracts for explicit research monitoring; no implicit report memory."""

from datetime import datetime
from typing import Literal

from plugin_runtime.common import CamelModel
from pydantic import ConfigDict, Field, field_validator, model_validator

from .research_evidence import ResearchEvidence


class Closed(CamelModel):
    model_config = ConfigDict(extra="forbid")


class MonitorSource(Closed):
    source_id: str = Field(min_length=1, max_length=200)
    required: bool = True
    max_age_seconds: int = Field(ge=1, le=31536000)
    event_id: str | None = None
    contract_id: str | None = None


class MetricRule(Closed):
    concept: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    direction: Literal["increase", "decrease", "either"]
    absolute_change: str = Field(min_length=1, max_length=120)

    @field_validator("absolute_change")
    @classmethod
    def positive_decimal(cls, value):
        from decimal import Decimal

        from .research_evidence import decimal_text

        decimal_text(value)
        if Decimal(value) <= 0:
            raise ValueError("threshold_must_be_positive")
        return value


class MonitorEvent(Closed):
    venue: Literal["polymarket", "kalshi"]
    event_id: str | None = Field(default=None, min_length=1, max_length=160)
    contract_id: str | None = Field(default=None, min_length=1, max_length=160)
    hypothesis: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def identity_required(self):
        if not self.event_id and not self.contract_id:
            raise ValueError("event_or_contract_required")
        return self


class MonitorScope(Closed):
    symbol: str = Field(min_length=1, max_length=24)
    cik: str = Field(min_length=10, max_length=10)

    @field_validator("cik")
    @classmethod
    def numeric_cik(cls, value):
        if not value.isascii() or not value.isdigit():
            raise ValueError("invalid_cik")
        return value

    question: str = Field(min_length=1, max_length=2000)
    horizon_months: int = Field(ge=1, le=120)
    rule_version: str = Field(min_length=1, max_length=100)
    sources: list[MonitorSource] = Field(min_length=1, max_length=30)
    rules: list[MetricRule] = Field(default_factory=list, max_length=30)
    source_urls: list[str] = Field(default_factory=list, max_length=5)
    include_social: bool = False
    include_insider: bool = False
    include_prediction: bool = False
    macro_series_ids: list[str] = Field(
        default_factory=lambda: ["CPIAUCSL", "CPILFESL", "A191RL1Q225SBEA", "UNRATE", "FEDFUNDS"],
        max_length=5,
    )
    events: list[MonitorEvent] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def unique_sources(self):
        if self.include_prediction and not self.events:
            raise ValueError("prediction_events_required")
        ids = [source.source_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_monitor_source")
        return self


class Begin(Closed):
    monitor_key: str = Field(min_length=1, max_length=160)
    scope: MonitorScope


class BeginResult(Closed):
    snapshot_id: str = Field(min_length=1, max_length=36)
    cutoff_at: str
    as_of_date: str = Field(min_length=10, max_length=10)
    scope_hash: str


class Coverage(Closed):
    source_id: str
    complete: bool
    observed_at: datetime
    evidence_ids: list[str] = Field(default_factory=list, max_length=300)
    warning: str | None = None


class Change(Closed):
    kind: Literal[
        "new_disclosure", "fact_revision", "metric_threshold", "contract_changed", "contract_closed"
    ]
    evidence_id: str
    previous_evidence_id: str | None = None
    description: str


class Observe(Closed):
    snapshot_id: str
    evidence: list[ResearchEvidence] = Field(max_length=300)
    coverage: list[Coverage] = Field(max_length=30)


class ObservationResult(Closed):
    snapshot_id: str
    cutoff_at: str
    as_of_date: str = Field(min_length=10, max_length=10)
    state: Literal["no_baseline", "unchanged", "invalid", "changed"]
    should_research: bool
    changes: list[Change]
    warnings: list[str]
    previous_snapshot_id: str | None = None


class Attach(Closed):
    snapshot_id: str
    status: Literal["succeeded", "failed"]
    report_id: int | None = Field(default=None, ge=1)


class AttachResult(Closed):
    snapshot_id: str
    report_status: Literal["succeeded", "failed"]
    report_id: int | None = None
    report_digest: str | None = None

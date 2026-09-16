"""Research evidence v1 public value contract; independently owned Oracle projection."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from plugin_runtime.common import CamelModel, ensure_timezone
from pydantic import Field, field_validator, model_validator


def decimal_text(value: str) -> str:
    if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise ValueError("Expected a finite plain decimal string")
    return value


class PredictionObservation(CamelModel):
    venue: Literal["polymarket", "kalshi"]
    event_id: str = Field(max_length=160)
    contract_id: str = Field(min_length=1, max_length=160)
    outcome: str = Field(min_length=1, max_length=160)
    rule_version: str | None = Field(default=None, max_length=160)
    status: str = Field(min_length=1, max_length=80)
    deadline: datetime | None = None
    quote_type: Literal["bid_ask"] = "bid_ask"

    @field_validator("deadline")
    @classmethod
    def aware_time(cls, value):
        return ensure_timezone(value) if value is not None else value


class ResearchEvidence(CamelModel):
    schema_version: Literal["1"] = "1"
    evidence_id: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=160)
    kind: Literal["fact", "excerpt", "observation", "user"]
    title: str = Field(min_length=1, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    published_at: datetime | None = None
    publication_date: date | None = None
    available_by_date: date | None = None
    retrieved_at: datetime
    period_start: date | None = None
    period_end: date | None = None
    value: str | None = Field(default=None, max_length=120)
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    text: str | None = Field(default=None, max_length=12000)
    locator: str | None = Field(default=None, max_length=1000)
    accession: str | None = Field(default=None, max_length=80)
    metric: str | None = Field(default=None, max_length=160)
    verified: bool = False
    source_type: (
        Literal["sec", "official", "market", "news", "social", "prediction", "user"] | None
    ) = None
    uncertainty_reason: str | None = Field(default=None, max_length=1000)
    symbol: str | None = Field(default=None, max_length=30)
    currency: str | None = Field(default=None, max_length=12)
    taxonomy: str | None = Field(default=None, max_length=80)
    tag: str | None = Field(default=None, max_length=160)
    form: str | None = Field(default=None, max_length=40)
    fiscal_year: int | None = None
    fiscal_period: str | None = Field(default=None, max_length=20)
    formula: str | None = Field(default=None, max_length=500)
    input_evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    supersedes_evidence_id: str | None = Field(default=None, max_length=160)
    prediction: PredictionObservation | None = None

    @field_validator("published_at", "retrieved_at")
    @classmethod
    def aware_time(cls, value):
        return ensure_timezone(value) if value is not None else value

    @field_validator("value")
    @classmethod
    def finite_value(cls, value):
        return decimal_text(value) if value is not None else value

    @model_validator(mode="after")
    def consistent_fields(self):
        if self.published_at is not None and self.publication_date is not None:
            raise ValueError("Use publishedAt or publicationDate, not both")
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("periodStart exceeds periodEnd")
        if self.value is not None and not self.unit:
            raise ValueError("Numeric evidence requires unit")
        if (self.kind == "user" or self.source_type == "user") and self.verified:
            raise ValueError("User materials cannot be promoted to verified evidence")
        return self

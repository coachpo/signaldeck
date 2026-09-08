from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from finance_plugin.contracts import RuntimeToolWarning
from plugin_runtime.common import CamelModel, ensure_timezone
from plugin_runtime.formatting import normalize_symbol
from pydantic import Field, field_validator, model_validator

_NORMALIZED_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")


def _validate_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_timezone(value)


def _normalize_identifier(value: str, *, field_name: str) -> str:
    normalized = "_".join(value.strip().lower().split())
    if _NORMALIZED_IDENTIFIER_RE.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be a lowercase identifier")
    return normalized


def _normalize_symbols(values: Sequence[str]) -> list[str]:
    symbols: list[str] = []
    seen_symbols: set[str] = set()
    for raw_symbol in values:
        symbol = normalize_symbol(raw_symbol)
        if not symbol or symbol in seen_symbols:
            continue
        symbols.append(symbol)
        seen_symbols.add(symbol)
    return symbols


class SocialSentimentMetric(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    value: Decimal | str | None
    unit: str | None = Field(default=None, max_length=80)
    source: str | None = Field(default=None, max_length=120)
    as_of: datetime | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_identifier(value, field_name="Metric name")

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_identifier(value, field_name="Metric source")

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class SocialSentimentSourceBlock(CamelModel):
    source: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=300)
    summary: str | None = None
    url: str | None = None
    as_of: datetime | None = None
    symbols: list[str] = Field(default_factory=list)
    sentiment: Literal["positive", "neutral", "negative", "mixed"] | None = None
    metrics: list[SocialSentimentMetric] = Field(default_factory=list)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return _normalize_identifier(value, field_name="Source")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Provider is required")
        return normalized

    @field_validator("title", "summary", "url")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: list[str]) -> list[str]:
        return _normalize_symbols(value)


class SocialSentimentLookupResult(CamelModel):
    symbol: str
    sources: list[str] = Field(default_factory=list)
    start_date: datetime | None = None
    end_date: datetime | None = None
    source_blocks: list[SocialSentimentSourceBlock] = Field(default_factory=list)
    metrics: list[SocialSentimentMetric] = Field(default_factory=list)
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = normalize_symbol(value)
        if not normalized:
            raise ValueError("Social sentiment symbol is required")
        return normalized

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, value: list[str]) -> list[str]:
        sources: list[str] = []
        seen_sources: set[str] = set()
        for raw_source in value:
            source = _normalize_identifier(raw_source, field_name="Source")
            if source in seen_sources:
                continue
            sources.append(source)
            seen_sources.add(source)
        return sources

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_bounds(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)

    @model_validator(mode="after")
    def validate_date_bounds(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("startDate must be before or equal to endDate")
        return self


__all__ = [
    "SocialSentimentLookupResult",
    "SocialSentimentMetric",
    "SocialSentimentSourceBlock",
]

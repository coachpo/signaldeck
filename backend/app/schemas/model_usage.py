"""Reported model usage with explicit coverage, never provider billing estimates."""

from datetime import date as CalendarDate
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel


class ModelUsageSummary(CamelModel):
    model_calls: int = 0
    confirmed_calls: int = 0
    failed_calls: int = 0
    unconfirmed_calls: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    usage_known_calls: int = 0
    usage_missing_calls: int = 0
    duration_known_calls: int = 0
    network_attempts: int = 0
    failed_network_attempts: int = 0
    unconfirmed_network_attempts: int = 0
    usage_coverage: Literal["complete", "partial", "none"] = "none"


class ModelUsageBreakdown(CamelModel):
    resource_id: str
    model_id: str
    api_style: str
    summary: ModelUsageSummary


class ModelUsageRead(CamelModel):
    run_id: str | None = None
    run_status: str | None = None
    date: CalendarDate | None = None
    timezone: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    as_of: datetime
    run_duration_ms: int | None = None
    summary: ModelUsageSummary
    models: list[ModelUsageBreakdown] = Field(default_factory=list)

"""Schedule configuration and delivery status, without calendar execution logic."""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, JsonValue, field_validator

from app.schemas.common import CamelModel


class ScheduleDefinition(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    package_key: str = Field(min_length=1)
    workflow_key: str = Field(min_length=1)
    parameters: JsonValue = Field(default_factory=dict)
    cron: str = Field(min_length=1, max_length=256)
    time_zone: str = "UTC"
    overlap_policy: Literal["skip", "buffer_one", "allow"] = "skip"
    catchup_window_seconds: int = Field(default=60, ge=10)
    paused: bool = False

    @field_validator("time_zone")
    @classmethod
    def valid_time_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Use an IANA time zone") from exc
        return value

    @field_validator("cron")
    @classmethod
    def explicit_calendar(cls, value: str) -> str:
        value = value.strip()
        if "TZ=" in value or "\n" in value or "\r" in value:
            raise ValueError("Set the time zone separately from the cron expression")
        return value


class ScheduleRecord(ScheduleDefinition):
    id: str
    revision: int
    synced_revision: int
    sync_status: Literal["pending", "synced", "failed", "deleted"]
    sync_error_code: str | None = None
    desired_deleted: bool = False
    updated_at: datetime


class ScheduleTriggerReceipt(CamelModel):
    schedule_id: str
    trigger_id: str
    status: Literal["pending", "accepted", "failed"]
    error_code: str | None = None


class ScheduleFireRecord(CamelModel):
    trigger_id: str
    schedule_id: str
    scheduled_at: datetime
    engine_workflow_id: str
    engine_run_id: str
    status: Literal["pending", "launched", "launch_failed", "succeeded", "failed", "cancelled"]
    run_id: str | None = None
    error_code: str | None = None
    updated_at: datetime

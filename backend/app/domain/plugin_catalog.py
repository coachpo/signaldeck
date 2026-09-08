"""Plugin availability evidence is an observation, not a live-read side effect."""

from datetime import datetime
from typing import Literal

from app.schemas.common import CamelModel


class PluginObservation(CamelModel):
    status: Literal["not_observed", "succeeded", "failed", "unknown"] = "not_observed"
    observed_at: datetime | None = None
    error_code: str | None = None
    run_id: str | None = None
    operation_id: str | None = None
    evidence_id: str | None = None

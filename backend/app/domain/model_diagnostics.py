"""Closed, credential-free model observation contracts."""

from datetime import datetime
from typing import Literal

from app.schemas.common import CamelModel

ModelErrorCategory = Literal["quota", "authentication", "rate_limit", "model", "input", "unknown"]
MODEL_ERROR_CATEGORIES = {"quota", "authentication", "rate_limit", "model", "input", "unknown"}


class ModelObservation(CamelModel):
    status: Literal["not_observed", "succeeded", "failed", "unknown"] = "not_observed"
    observed_at: datetime | None = None
    error_code: str | None = None
    error_category: ModelErrorCategory | None = None
    run_id: str | None = None
    evidence_id: str | None = None


def model_binding_digest(binding: dict) -> str:
    """Normalize defaults exactly as Launch does; never hash credential values."""
    from app.domain.resources import ResolvedModelConfiguration
    from app.domain.tool_contracts import canonical_digest

    return canonical_digest(
        ResolvedModelConfiguration.model_validate(binding).model_dump(mode="json", by_alias=True)
    )

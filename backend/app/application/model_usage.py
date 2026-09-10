"""Aggregate one observation per logical model call with explicit missing values."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.schemas.model_usage import ModelUsageSummary


@dataclass(frozen=True)
class ModelCallUsage:
    id: str
    resource_id: str
    model_id: str
    api_style: str
    started_at: datetime
    status: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    attempt_statuses: tuple[str, ...]


def summarize_model_calls(calls: Sequence[ModelCallUsage]) -> ModelUsageSummary:
    # ModelResponse and its successful network attempt refer to the same usage.
    # Recovery reuses this identity rather than producing an additional charge.
    unique = list({call.id: call for call in calls}.values())
    inputs = [call.input_tokens for call in unique if call.input_tokens is not None]
    outputs = [call.output_tokens for call in unique if call.output_tokens is not None]
    durations = [call.duration_ms for call in unique if call.duration_ms is not None]
    known = sum(call.input_tokens is not None and call.output_tokens is not None for call in unique)
    attempts = [status for call in unique for status in call.attempt_statuses]
    return ModelUsageSummary(
        model_calls=len(unique),
        confirmed_calls=sum(call.status == "succeeded" for call in unique),
        failed_calls=sum(call.status == "failed" for call in unique),
        unconfirmed_calls=sum(call.status not in {"succeeded", "failed"} for call in unique),
        input_tokens=sum(inputs) if inputs or not unique else None,
        output_tokens=sum(outputs) if outputs or not unique else None,
        duration_ms=sum(durations) if durations or not unique else None,
        usage_known_calls=known,
        usage_missing_calls=len(unique) - known,
        duration_known_calls=len(durations),
        network_attempts=len(attempts),
        failed_network_attempts=attempts.count("failed"),
        unconfirmed_network_attempts=sum(
            status not in {"succeeded", "failed"} for status in attempts
        ),
        usage_coverage=(
            "complete" if known == len(unique) else "partial" if inputs or outputs else "none"
        ),
    )

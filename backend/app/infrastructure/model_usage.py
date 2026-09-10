"""Read stored logical call evidence without contacting providers or the engine."""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import DateTime, cast, or_, select

from app.application.model_usage import ModelCallUsage, summarize_model_calls
from app.domain.execution import ApplicationError
from app.infrastructure.artifact_store import ArtifactIntegrityError
from app.infrastructure.evidence_payloads import execution_value
from app.infrastructure.model_usage_capture import token_count
from app.infrastructure.platform_models import EvidenceRow, RunRow
from app.infrastructure.platform_store import PlatformStore
from app.schemas.model_usage import ModelUsageBreakdown, ModelUsageRead


def day_window(day: date, timezone: str) -> tuple[datetime, datetime]:
    if day == date.max:
        raise ApplicationError(
            "date_invalid", "Date must precede the final supported day", status=422
        )
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ApplicationError(
            "timezone_invalid", "Use a valid IANA timezone", status=422
        ) from None
    return (
        datetime.combine(day, time.min, zone).astimezone(UTC),
        datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(UTC),
    )


def _timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(UTC) if value else None


def _duration(start: datetime | None, end: datetime | None) -> int | None:
    return max(0, int((end - start).total_seconds() * 1000)) if start and end else None


def _reported_usage(row: dict[str, Any], store: PlatformStore) -> tuple[int | None, int | None]:
    if row["status"] != "succeeded":
        return None, None
    metadata = row.get("metadata", {})
    if "usage" in metadata:
        usage = metadata["usage"]
        if isinstance(usage, dict):
            return token_count(usage.get("inputTokens")), token_count(usage.get("outputTokens"))
        return None, None
    # Old SDK responses default absent counters to zero. Positive recorded values
    # are usable; zero has no presence evidence and must remain unknown.
    try:
        output = execution_value(row.get("output"), store.artifacts)
    except ArtifactIntegrityError:
        return None, None
    usage = output.get("usage") if isinstance(output, dict) else None
    if not isinstance(usage, dict):
        return None, None
    inputs, outputs = token_count(usage.get("input_tokens")), token_count(
        usage.get("output_tokens")
    )
    return inputs or None, outputs or None


def _identity(row: dict[str, Any], spec: dict[str, Any]) -> tuple[str, str, str]:
    node = spec["definition"]["workflows"][spec["workflowKey"]]["nodes"].get(row["nodeId"], {})
    agent = spec["definition"]["agents"].get(node.get("uses"), {})
    resource = agent.get("strategy", {}).get("modelRef", "unknown")
    binding = spec.get("modelBindings", {}).get(resource, {})
    return resource, binding.get("modelId", "unknown"), binding.get("apiStyle", "chat_completions")


def read_model_usage(
    store: PlatformStore,
    *,
    run_id: str | None = None,
    day: date | None = None,
    timezone: str = "UTC",
) -> ModelUsageRead:
    start, end = day_window(day, timezone) if day else (None, None)
    with store.session_factory() as session:
        run = session.get(RunRow, run_id) if run_id else None
        if run_id and run is None:
            raise ApplicationError("run_not_found", "Run is unavailable", status=404)
        query = select(EvidenceRow.payload).where(
            or_(
                EvidenceRow.payload["kind"].astext == "model",
                (EvidenceRow.payload["kind"].astext == "attempt")
                & (EvidenceRow.payload["metadata"]["networkKind"].astext == "model_request"),
            )
        )
        if run_id:
            query = query.where(EvidenceRow.run_id == run_id)
        elif start and end:
            candidates = select(EvidenceRow.run_id).where(
                cast(EvidenceRow.payload["startedAt"].astext, DateTime(timezone=True)) >= start,
                cast(EvidenceRow.payload["startedAt"].astext, DateTime(timezone=True)) < end,
            )
            query = query.where(EvidenceRow.run_id.in_(candidates))
        rows = list(session.scalars(query))
        specs: dict[str, dict[str, Any]] = {
            key: spec
            for key, spec in session.execute(
                select(RunRow.id, RunRow.spec).where(RunRow.id.in_({row["runId"] for row in rows}))
            ).all()
        }
        response = ModelUsageRead(
            run_id=run_id,
            run_status=run.status if run else None,
            date=day,
            timezone=timezone if day else None,
            window_start=start,
            window_end=end,
            as_of=datetime.now(UTC),
            run_duration_ms=_duration(run.started_at, run.finished_at) if run else None,
            summary=summarize_model_calls([]),
        )
    attempts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["kind"] == "attempt":
            attempts[row["parentId"]].append(row)
    calls = []
    for row in rows:
        if row["kind"] != "model":
            continue
        network = attempts[row["id"]]
        starts = [stamp for item in [row, *network] if (stamp := _timestamp(item.get("startedAt")))]
        if not starts:
            continue
        started_at = min(starts)
        if start and end and not start <= started_at < end:
            continue
        inputs, outputs = _reported_usage(row, store)
        resource, model, style = _identity(row, specs[row["runId"]])
        calls.append(
            ModelCallUsage(
                id=row["id"],
                resource_id=resource,
                model_id=model,
                api_style=style,
                started_at=started_at,
                status=row["status"],
                input_tokens=inputs,
                output_tokens=outputs,
                duration_ms=(
                    _duration(started_at, _timestamp(row.get("finishedAt")))
                    if row["status"] in {"succeeded", "failed", "cancelled"}
                    else None
                ),
                attempt_statuses=tuple(
                    item["status"]
                    for item in network
                    if item.get("metadata", {}).get("networkStarted") is not False
                ),
            )
        )
    response.summary = summarize_model_calls(calls)
    groups: dict[tuple[str, str, str], list[ModelCallUsage]] = defaultdict(list)
    for call in calls:
        groups[(call.resource_id, call.model_id, call.api_style)].append(call)
    response.models = [
        ModelUsageBreakdown(
            resource_id=key[0],
            model_id=key[1],
            api_style=key[2],
            summary=summarize_model_calls(value),
        )
        for key, value in sorted(groups.items())
    ]
    return response

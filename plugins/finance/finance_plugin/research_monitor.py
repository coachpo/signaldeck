"""Journaled monitoring tools with explicit immutable observation identities."""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from plugin_runtime.serialization import model_wire_schema, project
from plugin_runtime.server import digest, tool
from sqlalchemy import select, text

from .models.report import Report
from .models.research_monitor import ResearchHead, ResearchSnapshot
from .research_monitor_compare import changes_since, usable_evidence, validate_observation
from .research_monitor_contracts import (
    Attach,
    AttachResult,
    Begin,
    BeginResult,
    MonitorScope,
    ObservationResult,
    Observe,
)
from .research_monitor_prediction import prediction_changes

PREFIX = "signaldeck/finance/"
CONTRACTS = {
    "monitor_begin": (Begin, BeginResult, "Freeze a new explicit research observation cutoff."),
    "monitor_observe": (
        Observe,
        ObservationResult,
        "Validate evidence and compare the prior valid observation.",
    ),
    "monitor_report_attach": (
        Attach,
        AttachResult,
        "Bind a report outcome to its exact research observation.",
    ),
}


def definitions():
    return [
        tool(
            "signaldeck/finance",
            name,
            model_wire_schema(input_model),
            model_wire_schema(output_model),
            description,
            write=True,
        )
        for name, (input_model, output_model, description) in CONTRACTS.items()
    ]


def _lock(session, monitor_key, scope_hash):
    key = int.from_bytes(
        hashlib.sha256(f"monitor:{monitor_key}:{scope_hash}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _scope(payload):
    scope = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
    scope["symbol"] = scope["symbol"].upper()
    scope["sources"] = sorted(scope["sources"], key=lambda s: s["sourceId"])
    scope["rules"] = sorted(scope["rules"], key=digest)
    scope["events"] = sorted(scope["events"], key=digest)
    scope["sourceUrls"] = sorted(set(scope["sourceUrls"]))
    scope["macroSeriesIds"] = sorted(set(scope["macroSeriesIds"]))
    return scope


def _begin(session, payload, invocation):
    scope = _scope(payload.scope)
    scope_hash = digest(scope)
    _lock(session, payload.monitor_key, scope_hash)
    cutoff = datetime.now(UTC)
    record = ResearchSnapshot(
        id=str(uuid4()),
        monitor_key=payload.monitor_key,
        scope_hash=scope_hash,
        cutoff_at=cutoff,
        scope=scope,
        run_id=invocation["runId"],
    )
    session.add(record)
    return BeginResult(
        snapshot_id=record.id,
        cutoff_at=cutoff.isoformat(),
        as_of_date=cutoff.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
        scope_hash=scope_hash,
    )


def _snapshot(session, identity, invocation):
    record = session.get(ResearchSnapshot, identity)
    if record is None:
        raise ValueError("monitor_snapshot_not_found")
    if record.run_id != invocation["runId"]:
        raise ValueError("monitor_snapshot_run_mismatch")
    _lock(session, record.monitor_key, record.scope_hash)
    session.refresh(record)
    return record


def _observe(session, payload, invocation):
    record = _snapshot(session, payload.snapshot_id, invocation)
    if record.observation is not None:
        raise ValueError("monitor_snapshot_already_observed")
    scope = MonitorScope.model_validate(record.scope)
    valid, warnings = validate_observation(scope, payload, record.cutoff_at)
    previous = session.scalar(
        select(ResearchSnapshot)
        .where(
            ResearchSnapshot.monitor_key == record.monitor_key,
            ResearchSnapshot.scope_hash == record.scope_hash,
            ResearchSnapshot.cutoff_at < record.cutoff_at,
            ResearchSnapshot.observation.is_not(None),
            ResearchSnapshot.observation["state"].astext != "invalid",
        )
        .order_by(ResearchSnapshot.cutoff_at.desc())
        .limit(1)
    )
    changes = []
    if previous is not None:
        previous_payload = Observe.model_validate(previous.evidence)
        contract_changes, contract_warnings = prediction_changes(
            usable_evidence(scope, payload, []),
            usable_evidence(scope, previous_payload, []),
            record.cutoff_at,
            previous.cutoff_at,
        )
        warnings.extend(contract_warnings)
    else:
        contract_changes = []
    if not valid:
        state = "invalid"
    elif previous is None:
        state = "no_baseline"
    else:
        changes = contract_changes + changes_since(
            scope,
            usable_evidence(scope, payload, warnings),
            usable_evidence(
                scope, Observe.model_validate(previous.evidence), previous.observation["warnings"]
            ),
        )
        state = "changed" if changes else "unchanged"
    result = ObservationResult(
        snapshot_id=record.id,
        cutoff_at=record.cutoff_at.isoformat(),
        as_of_date=record.cutoff_at.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
        state=state,
        should_research=state in {"no_baseline", "changed"},
        changes=changes,
        warnings=warnings,
        previous_snapshot_id=previous.id if previous else None,
    )
    record.evidence = payload.model_dump(mode="json", by_alias=True)
    record.observation = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    record.previous_snapshot_id = previous.id if previous else None
    if valid:
        key = (record.monitor_key, record.scope_hash)
        head = session.get(ResearchHead, key)
        if head is None:
            session.add(
                ResearchHead(
                    monitor_key=record.monitor_key,
                    scope_hash=record.scope_hash,
                    snapshot_id=record.id,
                    cutoff_at=record.cutoff_at,
                )
            )
        elif head.cutoff_at < record.cutoff_at:
            head.snapshot_id, head.cutoff_at = record.id, record.cutoff_at
    return result


def _attach(session, payload, invocation):
    record = _snapshot(session, payload.snapshot_id, invocation)
    if record.observation is None or not record.observation["shouldResearch"]:
        raise ValueError("monitor_observation_not_researchable")
    if record.report_status != "pending":
        raise ValueError("monitor_report_already_attached")
    if payload.status == "succeeded":
        report = session.get(Report, payload.report_id) if payload.report_id else None
        if report is None:
            raise ValueError("monitor_report_not_found")
        if report.metadata_.get("createdBy", {}).get("runId") != record.run_id:
            raise ValueError("monitor_report_run_mismatch")
        # Explicit report metadata proves which observation the report consumed.
        if report.metadata_.get("researchSnapshotId") != record.id:
            raise ValueError("monitor_report_snapshot_mismatch")
        record.report_id, record.report_digest = report.id, digest(report.content)
    elif payload.report_id is not None:
        raise ValueError("monitor_failed_report_has_id")
    record.report_status = payload.status
    return AttachResult(
        snapshot_id=record.id,
        report_status=record.report_status,
        report_id=record.report_id,
        report_digest=record.report_digest,
    )


def execute(name, arguments, invocation, journal):
    short = name.removeprefix(PREFIX)
    model = CONTRACTS[short][0]
    payload = model.model_validate(arguments)
    handler = {
        "monitor_begin": _begin,
        "monitor_observe": _observe,
        "monitor_report_attach": _attach,
    }[short]

    def effect(session):
        return project(handler(session, payload, invocation).model_dump(mode="json", by_alias=True))

    return journal.write(
        invocation["operationId"],
        PREFIX + short,
        arguments,
        effect,
        scope=invocation.get("resourceBindings", {}),
    )


def validate_report_snapshot(session, snapshot_id, invocation):
    """Require the exact valid observation before persisting its research report."""
    record = _snapshot(session, snapshot_id, invocation)
    if record.observation is None or not record.observation["shouldResearch"]:
        raise ValueError("monitor_observation_not_researchable")
    if record.report_status != "pending":
        raise ValueError("monitor_report_already_attached")
    return record

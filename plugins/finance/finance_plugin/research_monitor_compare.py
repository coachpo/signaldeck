"""Deterministic freshness and material-change rules for selected evidence only."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from .research_monitor_contracts import Change
from .research_monitor_prediction import comparable_quote


def validate_observation(scope, payload, cutoff):
    warnings, valid = [], True
    evidence = {e.evidence_id: e for e in payload.evidence}
    if len(evidence) != len(payload.evidence):
        return False, ["duplicate_evidence_identity"]
    coverage = {c.source_id: c for c in payload.coverage}
    if len(coverage) != len(payload.coverage):
        return False, ["duplicate_source_coverage"]
    selected = set()
    for source in scope.sources:
        item = coverage.get(source.source_id)
        good = item is not None and item.complete
        if item is not None:
            if item.warning:
                warnings.append(item.warning)
            observed = item.observed_at
            good = good and observed.tzinfo is not None
            if observed.tzinfo is not None:
                good = good and cutoff - timedelta(
                    seconds=source.max_age_seconds
                ) <= observed <= datetime.now(UTC)
            for identity in item.evidence_ids:
                selected.add(identity)
                row = evidence.get(identity)
                good = good and row is not None
                if row is None:
                    continue
                good = good and row.verified and row.kind != "user"
                good = good and cutoff - timedelta(
                    seconds=source.max_age_seconds
                ) <= row.retrieved_at <= datetime.now(UTC)
                # Retrieval can finish after begin, but public availability cannot.
                if row.published_at is not None:
                    good = good and row.published_at < cutoff
                elif row.publication_date is not None:
                    good = (
                        good
                        and row.publication_date
                        < cutoff.astimezone(ZoneInfo("America/New_York")).date()
                    )
                elif row.available_by_date is not None:
                    known_by = datetime.combine(
                        row.available_by_date + timedelta(days=1),
                        time.min,
                        tzinfo=ZoneInfo("America/New_York"),
                    )
                    good = good and known_by <= cutoff
                else:
                    good = False
                if row.symbol and row.symbol.upper() != scope.symbol.upper():
                    good = False
        if not good:
            warnings.append(
                f"{'required' if source.required else 'optional'}_source_invalid:{source.source_id}"
            )
            valid = valid and not source.required
    attributed = {identity for item in payload.coverage for identity in item.evidence_ids}
    if set(evidence) != attributed:
        valid = False
        warnings.append("evidence_coverage_mismatch")
    if not selected.intersection(evidence):
        valid = False
        warnings.append("empty_evidence")
    return valid, warnings


def identity(row):
    return (
        row.source_type,
        row.metric,
        row.unit,
        row.currency,
        row.taxonomy,
        row.tag,
        row.period_start if row.source_type in {"sec", "official"} else None,
        row.period_end if row.source_type in {"sec", "official"} else None,
        row.symbol,
        row.source_id if row.source_type not in {"sec", "official"} or not row.metric else None,
        row.locator if not row.metric else None,
    )


def changes_since(scope, current, previous):
    old_documents = {e.source_id for e in previous if e.source_type in {"sec", "official"}}

    def latest(rows):
        ordered = sorted(
            rows,
            key=lambda e: (
                str(e.period_end or "") if e.source_type not in {"sec", "official"} else "",
                str(e.published_at or e.publication_date or e.available_by_date or ""),
                e.source_id,
                e.evidence_id,
            ),
        )
        return {identity(e): e for e in ordered if e.metric or e.locator}

    old, selected = latest(previous), latest(current)
    changes, disclosed = [], set()
    for row in sorted(current, key=lambda e: e.evidence_id):
        if not row.verified:
            continue
        prior = old.get(identity(row)) if selected.get(identity(row)) is row else None
        if row.source_type in {"sec", "official"}:
            if row.source_id not in old_documents and row.source_id not in disclosed:
                changes.append(
                    Change(
                        kind="new_disclosure",
                        evidence_id=row.evidence_id,
                        description="New selected official disclosure",
                    )
                )
                disclosed.add(row.source_id)
            if (
                prior is None
                and selected.get(identity(row)) is row
                and row.source_id in old_documents
                and row.metric
                and row.value is not None
                and row.period_end is not None
                and any(
                    e.source_id == row.source_id
                    and e.metric == row.metric
                    and e.unit == row.unit
                    and e.currency == row.currency
                    and e.period_end is not None
                    and e.period_end < row.period_end
                    for e in previous
                )
                and not any(identity(e) == identity(row) for e in previous)
            ):
                changes.append(
                    Change(
                        kind="new_disclosure",
                        evidence_id=row.evidence_id,
                        description="New selected official observation period",
                    )
                )
            if prior and (row.value, row.text, row.unit) != (prior.value, prior.text, prior.unit):
                changes.append(
                    Change(
                        kind="fact_revision",
                        evidence_id=row.evidence_id,
                        previous_evidence_id=prior.evidence_id,
                        description="Selected official fact changed",
                    )
                )
        elif (
            prior
            and row.value is not None
            and prior.value is not None
            and comparable_quote(row, prior)
        ):
            delta = Decimal(row.value) - Decimal(prior.value)
            for rule in scope.rules:
                if row.metric != rule.concept or row.unit != rule.unit:
                    continue
                directed = (
                    delta
                    if rule.direction == "increase"
                    else -delta if rule.direction == "decrease" else abs(delta)
                )
                if directed > 0 and directed >= Decimal(rule.absolute_change):
                    changes.append(
                        Change(
                            kind="metric_threshold",
                            evidence_id=row.evidence_id,
                            previous_evidence_id=prior.evidence_id,
                            description=f"{rule.concept}: change {delta} {rule.unit}",
                        )
                    )
                    break
    return changes[:100]


def usable_evidence(scope, payload, warnings):
    excluded = {
        warning.split(":", 1)[1]
        for warning in warnings
        if warning.startswith(("optional_source_invalid:", "required_source_invalid:"))
    }
    identities = {
        identity
        for row in payload.coverage
        if row.source_id not in excluded
        and row.source_id in {source.source_id for source in scope.sources}
        for identity in row.evidence_ids
    }
    return [row for row in payload.evidence if row.evidence_id in identities]

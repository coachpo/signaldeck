"""Prediction contract changes are distinct from comparable quote movement."""

from .research_monitor_contracts import Change

CLOSED = {"closed", "settled", "resolved", "finalized", "expired"}


def prediction_identity(row):
    meta = row.prediction
    return meta.venue, meta.event_id, meta.contract_id, meta.outcome


def prediction_changes(current, previous, cutoff, previous_cutoff):
    old = {prediction_identity(row): row for row in previous if row.prediction is not None}
    changes, warnings = [], []
    for row in current:
        meta = row.prediction
        if meta is None:
            continue
        prior = old.get(prediction_identity(row))
        if prior is None:
            continue
        before = prior.prediction
        kind = None
        expired = meta.deadline is not None and previous_cutoff < meta.deadline <= cutoff
        if expired or (meta.status.lower() in CLOSED and before.status != meta.status):
            kind = "contract_closed"
        elif (meta.rule_version, meta.status, meta.deadline, meta.quote_type) != (
            before.rule_version,
            before.status,
            before.deadline,
            before.quote_type,
        ):
            kind = "contract_changed"
        if kind:
            if row.verified and prior.verified:
                changes.append(
                    Change(
                        kind=kind,
                        evidence_id=row.evidence_id,
                        previous_evidence_id=prior.evidence_id,
                        description=(
                            "Prediction contract rules, status or deadline changed; "
                            "quotes require a comparable baseline"
                        ),
                    )
                )
            else:
                warnings.append(f"{kind}_unverified:{row.evidence_id}")
    return changes, warnings


def comparable_quote(current, previous):
    if current.prediction is None or previous.prediction is None:
        return current.prediction is None and previous.prediction is None
    left, right = current.prediction, previous.prediction
    return (
        prediction_identity(current) == prediction_identity(previous)
        and left.rule_version is not None
        and left.rule_version == right.rule_version
        and left.quote_type == right.quote_type
        and left.status.lower() not in CLOSED
        and right.status.lower() not in CLOSED
        and (left.deadline is None or current.retrieved_at < left.deadline)
        and (right.deadline is None or previous.retrieved_at < right.deadline)
        and current.source_id == previous.source_id
        and current.verified
        and previous.verified
    )

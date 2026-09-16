"""Project prediction rule and quote identity into the shared evidence contract."""

from .research_documents import digest
from .research_documents_evidence import PredictionObservation, ResearchEvidence


def prediction_evidence(snap) -> ResearchEvidence:
    return ResearchEvidence(
        evidence_id=digest(
            (
                snap.source_id
                + snap.outcome
                + snap.document_digest
                + str(snap.quoted_at)
                + str(snap.bid)
            ).encode()
        ),
        source_id=snap.source_id,
        kind="observation",
        title=f"{snap.contract_id} {snap.outcome} observation",
        url=snap.url,
        retrieved_at=snap.retrieved_at,
        published_at=snap.quoted_at if snap.bid is not None else None,
        value=snap.bid,
        unit="probability" if snap.bid is not None else None,
        metric="prediction_bid:"
        + digest((snap.source_id + snap.outcome).encode())
        + ":"
        + (snap.rule_version or "unknown"),
        verified=bool(
            snap.bid is not None and snap.quoted_at and snap.rule_version and not snap.gaps
        ),
        prediction=PredictionObservation(
            venue=snap.venue,
            event_id=snap.event_id,
            contract_id=snap.contract_id,
            outcome=snap.outcome,
            rule_version=snap.rule_version,
            status=snap.status,
            deadline=snap.deadline,
            quote_type=snap.quote_type,
        ),
        source_type="prediction",
        text=snap.rules,
        locator=f"contract {snap.contract_id}; outcome {snap.outcome}",
        uncertainty_reason="; ".join(snap.gaps) or None,
    )

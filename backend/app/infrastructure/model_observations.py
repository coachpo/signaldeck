"""Offline observation of actual model attempts bound to captured resource identity."""

from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.model_diagnostics import (
    MODEL_ERROR_CATEGORIES,
    ModelObservation,
    model_binding_digest,
)
from app.infrastructure.platform_models import EvidenceRow


def latest_model_observation(
    session: Session, resource_id: str, config: dict[str, Any], credential_revision: str
) -> dict[str, Any]:
    try:
        digest = model_binding_digest({**config, "credentialRevision": credential_revision})
    except ValidationError:
        return ModelObservation().model_dump(mode="json", by_alias=True)
    row = session.scalar(
        select(EvidenceRow.payload)
        .where(
            EvidenceRow.payload["kind"].astext == "attempt",
            EvidenceRow.payload["metadata"]["networkKind"].astext == "model_request",
            EvidenceRow.payload["metadata"]["resourceId"].astext == resource_id,
            EvidenceRow.payload["metadata"]["modelBindingDigest"].astext == digest,
            EvidenceRow.payload["metadata"]["networkStarted"].astext.is_distinct_from("false"),
            EvidenceRow.payload["finishedAt"].astext.is_not(None),
        )
        .order_by(EvidenceRow.payload["finishedAt"].astext.desc(), EvidenceRow.id.desc())
        .limit(1)
    )
    if row is None:
        observation = ModelObservation()
    else:
        category = row.get("metadata", {}).get("errorCategory")
        observation = ModelObservation.model_validate(
            {
                "status": (
                    row["status"]
                    if row["status"] in {"succeeded", "failed", "unknown"}
                    else "unknown"
                ),
                "observedAt": row["finishedAt"],
                "errorCode": row.get("errorCode"),
                "errorCategory": (
                    category
                    if isinstance(category, str) and category in MODEL_ERROR_CATEGORIES
                    else ("unknown" if row.get("errorCode") else None)
                ),
                "runId": row["runId"],
                "evidenceId": row["id"],
            }
        )
    return observation.model_dump(mode="json", by_alias=True)

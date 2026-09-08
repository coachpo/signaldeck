"""Append-safe execution evidence projection with immutable call ownership."""

from copy import deepcopy

from sqlalchemy.orm import Session, sessionmaker

from app.domain.execution import ApplicationError, ExecutionEvidence
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.evidence_payloads import persist_value
from app.infrastructure.platform_models import EvidenceRow, RunRow
from app.infrastructure.platform_transactions import lock_identity

TERMINAL = {"succeeded", "failed", "blocked", "skipped", "cancelled", "timed_out"}
IDENTITY_FIELDS = (
    "runId",
    "parentId",
    "nodeId",
    "kind",
    "attempt",
    "operationId",
    "toolId",
    "input",
)


def save_evidence(
    session: Session, evidence: ExecutionEvidence, artifacts: ArtifactStore | None = None
) -> None:
    payload = evidence.model_dump(mode="json", by_alias=True)
    payload["input"] = persist_value(payload["input"], artifacts)
    payload["output"] = persist_value(payload["output"], artifacts)
    lock_identity(session, "evidence:" + evidence.id)
    row = session.get(EvidenceRow, evidence.id)
    if row is not None:
        if any(row.payload.get(key) != payload.get(key) for key in IDENTITY_FIELDS):
            raise ApplicationError(
                "evidence_identity_conflict", "Evidence identity differs", status=409
            )
        if row.payload["status"] in TERMINAL:
            # Timestamp replay differences cannot alter a confirmed execution result.
            stable = ("status", "output", "errorCode", "metadata")
            if any(row.payload.get(key) != payload.get(key) for key in stable):
                raise ApplicationError(
                    "evidence_result_conflict", "Confirmed evidence is immutable", status=409
                )
            return
        row.payload = payload
        return
    if session.get(RunRow, evidence.run_id) is None:
        raise ApplicationError("run_not_found", "Evidence run is unavailable", status=404)
    expected_parent = {"node": None, "agent": "node", "model": "agent", "tool": "agent"}
    if evidence.kind == "node" and evidence.parent_id is not None:
        raise ApplicationError(
            "evidence_parent_invalid", "Node evidence belongs directly to its run", status=409
        )
    if evidence.kind != "node" and evidence.parent_id is None:
        raise ApplicationError(
            "evidence_parent_invalid", "Call evidence requires its owner", status=409
        )
    if evidence.parent_id is not None:
        parent = session.get(EvidenceRow, evidence.parent_id)
        if (
            parent is None
            or parent.run_id != evidence.run_id
            or parent.id == evidence.id
            or parent.payload["nodeId"] != evidence.node_id
            or (evidence.kind == "attempt" and parent.payload["kind"] not in {"model", "tool"})
            or (
                evidence.kind != "attempt"
                and parent.payload["kind"] != expected_parent[evidence.kind]
            )
        ):
            raise ApplicationError(
                "evidence_parent_invalid", "Evidence parent is unavailable", status=409
            )
    session.add(
        EvidenceRow(
            id=evidence.id, run_id=evidence.run_id, parent_id=evidence.parent_id, payload=payload
        )
    )


class EvidenceStore:
    session_factory: sessionmaker[Session]
    artifacts: ArtifactStore | None = None

    def record_evidence(self, evidence: ExecutionEvidence) -> None:
        with self.session_factory() as session, session.begin():
            save_evidence(session, evidence, self.artifacts)

    def record_evidence_batch(self, evidence: list[ExecutionEvidence]) -> None:
        """Confirm related call facts atomically, with parents preceding new children."""
        with self.session_factory() as session, session.begin():
            for identity in sorted({item.id for item in evidence}):
                lock_identity(session, "evidence:" + identity)
            for item in evidence:
                save_evidence(session, item, self.artifacts)
                session.flush()

    def get_evidence(self, evidence_id: str) -> ExecutionEvidence | None:
        with self.session_factory() as session:
            row = session.get(EvidenceRow, evidence_id)
            return None if row is None else ExecutionEvidence.model_validate(deepcopy(row.payload))

"""Atomic application of observed engine completion to unfinished run projections."""

from copy import deepcopy

from sqlalchemy import select

from app.application.execution_projection import EngineTerminalFact
from app.domain.execution import RunSummary
from app.infrastructure.evidence_payloads import persist_value
from app.infrastructure.evidence_records import EvidenceStore
from app.infrastructure.platform_models import EvidenceRow, OperationRow, RunRow
from app.infrastructure.platform_transactions import lock_identity


class PlatformProjectionStore(EvidenceStore):
    def list_unfinished_runs(self) -> list[RunSummary]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(RunRow)
                .where(RunRow.status.in_(["queued", "running"]))
                .order_by(RunRow.created_at, RunRow.id)
            )
            return [
                RunSummary.model_validate(
                    {
                        "id": row.id,
                        "packageKey": row.spec["packageKey"],
                        "workflowKey": row.spec["workflowKey"],
                        "packageHash": row.spec["packageHash"],
                        "status": row.status,
                        "createdAt": row.created_at,
                        "startedAt": row.started_at,
                        "finishedAt": row.finished_at,
                        "cancelRequestedAt": row.cancel_requested_at,
                        "origin": row.spec["origin"],
                    }
                )
                for row in rows
            ]

    def project_engine_terminal(self, run_id: str, fact: EngineTerminalFact) -> bool:
        with self.session_factory() as session, session.begin():
            row = session.get(RunRow, run_id, with_for_update=True)
            if row is None or row.status not in {"queued", "running"}:
                return False
            ids = session.scalars(
                select(EvidenceRow.id).where(EvidenceRow.run_id == run_id).order_by(EvidenceRow.id)
            ).all()
            for identity in ids:
                lock_identity(session, "evidence:" + identity)
            for identity in ids:
                evidence = session.get(EvidenceRow, identity)
                assert evidence is not None
                if evidence.payload["status"] not in {"pending", "running", "unknown"}:
                    continue
                payload = deepcopy(evidence.payload)
                is_call = payload["kind"] in {"model", "tool", "attempt"}
                payload["status"] = "unknown" if is_call else fact.interrupted_status
                payload["finishedAt"] = payload.get("finishedAt") or fact.finished_at.isoformat()
                payload["errorCode"] = payload.get("errorCode") or (
                    "engine_stopped_result_unconfirmed" if is_call else fact.error_code
                )
                payload["metadata"] = {
                    **payload.get("metadata", {}),
                    "engineTerminalReason": fact.error_code,
                    "observedFromEngine": True,
                }
                evidence.payload = payload
                if payload["kind"] == "tool":
                    operation = session.get(OperationRow, identity)
                    if operation is not None and operation.payload["status"] != "succeeded":
                        updated = deepcopy(operation.payload)
                        updated["status"] = "unknown"
                        result = updated.get("result") or {}
                        updated["result"] = {
                            "status": "unknown",
                            "output": result.get("output"),
                            "code": result.get("code") or "engine_stopped_result_unconfirmed",
                            "retryable": False,
                        }
                        operation.payload = updated
            row.status, row.error_code = fact.status, fact.error_code
            row.output = persist_value(fact.output, self.artifacts)
            row.finished_at = fact.finished_at
            return True

"""Read-only fact projection; read receipts never advance execution or hide unknown effects."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import or_, select

from app.application.effect_projection import unknown_evidence
from app.application.model_failure_projection import project_model_failure
from app.domain.execution import ApplicationError, ExecutionEvidence
from app.infrastructure.platform_models import EvidenceRow, RunRow
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.platform_transactions import lock_identity
from app.infrastructure.result_metadata_store import AttentionReceiptRow
from app.infrastructure.schedule_fires import ScheduleFireRow
from app.schemas.attention import AttentionItem, AttentionList, AttentionReadPatch


def _identity(facts: object) -> str:
    return hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()


def _time(value: object, fallback: datetime) -> datetime:
    if not isinstance(value, str):
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return fallback


class AttentionStore:
    def __init__(self, platform: PlatformStore):
        self.platform = platform

    def _items(self, snapshot_at: datetime) -> list[AttentionItem]:
        unresolved = (
            select(EvidenceRow.id)
            .where(
                EvidenceRow.run_id == RunRow.id,
                EvidenceRow.payload["kind"].astext != "attempt",
                EvidenceRow.payload["status"].astext == "unknown",
            )
            .exists()
        )
        with self.platform.session_factory() as session:
            runs = list(
                session.scalars(
                    select(RunRow).where(
                        RunRow.created_at <= snapshot_at,
                        or_(RunRow.status.in_(("succeeded", "failed", "cancelled")), unresolved),
                    )
                )
            )
            evidence: dict[str, list[tuple[str, dict]]] = {}
            if runs:
                for row in session.scalars(
                    select(EvidenceRow).where(
                        EvidenceRow.run_id.in_([run.id for run in runs]),
                        EvidenceRow.payload["kind"].astext != "attempt",
                    )
                ):
                    evidence.setdefault(row.run_id, []).append((row.id, row.payload))
            items: list[AttentionItem] = []
            for run in runs:
                records = sorted(evidence.get(run.id, []))
                facts = [(eid, p.get("status"), p.get("errorCode")) for eid, p in records]
                # An unresolved logical operation becoming confirmed changes this identity
                # even when the Run's terminal status and ID remain unchanged.
                identity = _identity(["run", run.id, run.status, run.finished_at, facts])
                writes, reads = unknown_evidence(run.spec, [p for _, p in records])
                occurred = max(
                    [run.finished_at or run.created_at]
                    + [_time(p.get("finishedAt"), run.created_at) for _, p in records]
                )
                category = project_model_failure(
                    run.error_code,
                    [ExecutionEvidence.model_validate(payload) for _, payload in records],
                )
                if occurred > snapshot_at:
                    continue
                items.append(
                    AttentionItem(
                        id=identity,
                        kind="run",
                        title=self.platform._summary(run).title,
                        status=run.status,
                        run_id=run.id,
                        occurred_at=occurred,
                        has_unknown_effects=bool(writes),
                        has_unknown_results=bool(reads),
                        error_code=run.error_code,
                        error_category=category,
                    )
                )
            for fire in session.scalars(
                select(ScheduleFireRow).where(
                    ScheduleFireRow.run_id.is_(None),
                    ScheduleFireRow.status.in_(("launch_failed", "failed")),
                    ScheduleFireRow.updated_at <= snapshot_at,
                )
            ):
                items.append(
                    AttentionItem(
                        id=_identity(
                            [
                                "fire",
                                fire.trigger_id,
                                fire.status,
                                fire.error_code,
                                fire.engine_workflow_id,
                                fire.engine_run_id,
                            ]
                        ),
                        kind="fire",
                        title="安排未能启动",
                        status=fire.status,
                        schedule_id=fire.schedule_id,
                        trigger_id=fire.trigger_id,
                        occurred_at=fire.updated_at,
                        error_code=fire.error_code,
                    )
                )
            receipts = (
                {
                    row.identity: row
                    for row in session.scalars(
                        select(AttentionReceiptRow).where(
                            AttentionReceiptRow.identity.in_([item.id for item in items])
                        )
                    )
                }
                if items
                else {}
            )
            for item in items:
                receipt = receipts.get(item.id)
                if receipt:
                    item.is_read, item.revision = receipt.is_read, receipt.revision
            return sorted(items, key=lambda item: (item.occurred_at, item.id), reverse=True)

    def list(
        self,
        *,
        view: Literal["all", "attention"] = "attention",
        limit: int = 25,
        offset: int = 0,
        snapshot_at: datetime | None = None,
    ) -> AttentionList:
        snapshot_at = snapshot_at or datetime.now(UTC)
        items = self._items(snapshot_at)
        if view == "attention":
            items = [item for item in items if not item.is_read or item.has_unknown_effects]
        return AttentionList(
            items=items[offset : offset + limit],
            total=len(items),
            limit=limit,
            offset=offset,
            snapshot_at=snapshot_at,
        )

    def mark(self, identity: str, payload: AttentionReadPatch) -> AttentionItem:
        item = next((item for item in self._items(datetime.now(UTC)) if item.id == identity), None)
        if item is None:
            raise ApplicationError(
                "attention_changed", "Execution state changed; refresh updates", status=409
            )
        with self.platform.session_factory() as session, session.begin():
            lock_identity(session, "attention-read:" + identity)
            row = session.get(AttentionReceiptRow, identity)
            revision = row.revision if row else 0
            if revision != payload.expected_revision:
                raise ApplicationError(
                    "attention_read_conflict", "Read status changed; refresh updates", status=409
                )
            if row is None:
                row = AttentionReceiptRow(identity=identity, revision=0)
                session.add(row)
            row.revision += 1
            row.is_read = payload.is_read
            row.updated_at = datetime.now(UTC)
            return item.model_copy(update={"is_read": row.is_read, "revision": row.revision})

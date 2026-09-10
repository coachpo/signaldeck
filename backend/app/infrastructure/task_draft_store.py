"""Independent mutable editor records; no execution or package mutation effects."""

import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.execution import ApplicationError
from app.infrastructure.platform_models import PlatformBase, RunRow
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.platform_transactions import lock_identity
from app.schemas.task_drafts import TaskDraftRead, TaskDraftWrite


class TaskDraftRow(PlatformBase):
    __tablename__ = "platform_task_drafts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def reject_credentials(payload: TaskDraftWrite) -> None:
    # Scan JSON key tokens even in unfinished text; do not echo values in errors.
    text = json.dumps(payload.parameters) + "\n" + (payload.json_text or "")
    for token in re.findall(r'"((?:[^"\\]|\\.)*)"\s*:', text):
        try:
            key = json.loads('"' + token + '"')
        except ValueError:
            key = token
        if re.sub(r"[^a-z]", "", key.lower()) in {
            "credentials",
            "credential",
            "password",
            "apikey",
            "secret",
            "clientsecret",
            "accesstoken",
            "refreshtoken",
            "authorization",
            "privatekey",
        }:
            raise ApplicationError(
                "credential_input", "Use a connection for credentials", status=422
            )


class TaskDraftStore:
    def __init__(self, platform: PlatformStore):
        self.platform = platform

    def _read(self, row: TaskDraftRow) -> TaskDraftRead:
        payload = row.payload
        package = self.platform.get_package(payload["package_key"], payload["package_hash"])
        assert package is not None
        current = self.platform.get_package(payload["package_key"])
        current_hash = None if current is None else current["packageHash"]
        return TaskDraftRead.model_validate(
            {
                **payload,
                "id": row.id,
                "revision": row.revision,
                "updated_at": row.updated_at,
                "current_package_hash": current_hash,
                "needs_revalidation": current_hash != payload["package_hash"],
                "workflow": package["definition"]["workflows"][payload["workflow_key"]],
            }
        )

    def get(self, identity: str) -> TaskDraftRead:
        with self.platform.session_factory() as session:
            row = session.get(TaskDraftRow, identity)
            if row is None:
                raise ApplicationError("draft_not_found", "Draft is unavailable", status=404)
            return self._read(row)

    def list(self) -> list[TaskDraftRead]:
        with self.platform.session_factory() as session:
            return [
                self._read(row)
                for row in session.scalars(
                    select(TaskDraftRow).order_by(TaskDraftRow.updated_at.desc(), TaskDraftRow.id)
                )
            ]

    def save(self, identity: str, payload: TaskDraftWrite) -> TaskDraftRead:
        reject_credentials(payload)
        package = self.platform.get_package(payload.package_key, payload.package_hash)
        if package is None or payload.workflow_key not in package["definition"]["workflows"]:
            raise ApplicationError(
                "draft_definition_missing", "Draft definition is unavailable", status=422
            )
        if payload.source_run_id is not None:
            with self.platform.session_factory() as session:
                source = session.get(RunRow, payload.source_run_id)
                if source is None or any(
                    source.spec[key] != value
                    for key, value in {
                        "packageKey": payload.package_key,
                        "workflowKey": payload.workflow_key,
                        "packageHash": payload.package_hash,
                    }.items()
                ):
                    raise ApplicationError(
                        "draft_source_mismatch",
                        "Source run does not match the draft definition",
                        status=422,
                    )
        data = payload.model_dump(mode="json", exclude={"revision"})
        with self.platform.session_factory() as session, session.begin():
            lock_identity(session, "draft:" + identity)
            row = session.get(TaskDraftRow, identity, with_for_update=True)
            if row is not None and row.payload == data:
                return self._read(row)
            if payload.revision != (0 if row is None else row.revision):
                raise ApplicationError(
                    "draft_conflict",
                    "Draft changed in another window; restore it or save a separate draft",
                    status=409,
                )
            if row is not None and row.payload["pending"]:
                stable = {
                    k: v for k, v in row.payload.items() if k not in {"pending", "binding_token"}
                }
                if stable != {
                    k: v for k, v in data.items() if k not in {"pending", "binding_token"}
                }:
                    raise ApplicationError(
                        "draft_pending", "Resolve the pending launch before editing", status=409
                    )
            if row is None:
                row = TaskDraftRow(id=identity, revision=0)
                session.add(row)
            row.payload = data
            row.revision += 1
            row.updated_at = datetime.now(UTC)
        return self.get(identity)

    def delete(self, identity: str, revision: int) -> None:
        with self.platform.session_factory() as session, session.begin():
            lock_identity(session, "draft:" + identity)
            row = session.get(TaskDraftRow, identity, with_for_update=True)
            if row is None:
                return
            if row.revision != revision:
                raise ApplicationError(
                    "draft_conflict", "Draft changed; restore it before deleting", status=409
                )
            if (
                row.payload["pending"]
                and session.scalar(
                    select(RunRow.id).where(RunRow.launch_id == row.payload["launch_id"])
                )
                is None
            ):
                raise ApplicationError(
                    "draft_pending", "Resolve the pending launch before deleting", status=409
                )
            session.delete(row)

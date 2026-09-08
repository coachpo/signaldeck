"""Durable, optional task bookmarks and validated input combinations."""

import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import JsonValue
from sqlalchemy import Boolean, DateTime, String, null, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, column_property, mapped_column

from app.domain.execution import ApplicationError
from app.domain.schema_contract import DomainValidationError, reject, validate_value
from app.infrastructure.platform_models import PackagePointerRow, PackageRevisionRow, PlatformBase
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.platform_transactions import lock_identity
from app.schemas.task_presets import TaskPresetCreate, TaskPresetRead, TaskPresetUpdate


class TaskPresetRow(PlatformBase):
    __tablename__ = "platform_task_presets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    package_key: Mapped[str] = mapped_column(String)
    workflow_key: Mapped[str] = mapped_column(String)
    package_hash: Mapped[str] = mapped_column(String)
    parameters: Mapped[JsonValue] = mapped_column(JSONB, nullable=True)
    explicit_null: Mapped[bool] = column_property(parameters.is_(None))
    is_favorite: Mapped[bool] = mapped_column(Boolean)
    is_pinned: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def validate_preset_parameters(schema: dict[str, Any], parameters: JsonValue) -> None:
    """Credentials belong to resource connections, never saved business inputs."""

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = re.sub(r"[^a-z]", "", key.lower())
                if normalized in {
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
                    reject("credential_input", "$.parameters", "Use a connection for credentials")
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(parameters)
    validate_value(schema, parameters, "$.parameters")


class TaskPresetStore:
    def __init__(self, platform: PlatformStore):
        self.platform = platform

    def _read(self, row: TaskPresetRow) -> TaskPresetRead:
        has_parameters = row.parameters is not None or row.explicit_null
        current = self.platform.get_package(row.package_key)
        workflow = (
            None if current is None else current["definition"]["workflows"].get(row.workflow_key)
        )
        status = "unavailable"
        errors = []
        if workflow is not None:
            status = "valid" if has_parameters else "not_applicable"
            if has_parameters:
                try:
                    validate_preset_parameters(workflow["inputSchema"], row.parameters)
                except DomainValidationError as exc:
                    status = "invalid"
                    errors = [
                        {"code": item.code, "path": item.path, "message": item.message}
                        for item in exc.diagnostics
                    ]
        return TaskPresetRead.model_validate(
            {
                **{
                    key: deepcopy(getattr(row, key))
                    for key in (
                        "id",
                        "name",
                        "package_key",
                        "workflow_key",
                        "package_hash",
                        "parameters",
                        "is_favorite",
                        "is_pinned",
                        "created_at",
                        "updated_at",
                    )
                },
                "has_parameters": has_parameters,
                "current_package_hash": None if current is None else current["packageHash"],
                "needs_revalidation": current is None or current["packageHash"] != row.package_hash,
                "validation_status": status,
                "validation_errors": errors,
            }
        )

    def list(self) -> list[TaskPresetRead]:
        with self.platform.session_factory() as session:
            return [
                self._read(row)
                for row in session.scalars(
                    select(TaskPresetRow).order_by(
                        TaskPresetRow.is_pinned.desc(),
                        TaskPresetRow.is_favorite.desc(),
                        TaskPresetRow.updated_at.desc(),
                        TaskPresetRow.id,
                    )
                )
            ]

    def get(self, preset_id: str) -> TaskPresetRead:
        with self.platform.session_factory() as session:
            row = session.get(TaskPresetRow, preset_id)
            if row is None:
                raise ApplicationError("preset_not_found", "Saved task is unavailable", status=404)
            return self._read(row)

    def save(
        self, payload: TaskPresetCreate | TaskPresetUpdate, preset_id: str | None = None
    ) -> TaskPresetRead:
        with self.platform.session_factory() as session, session.begin():
            row = (
                None
                if preset_id is None
                else session.get(TaskPresetRow, preset_id, with_for_update=True)
            )
            if preset_id is not None and row is None:
                raise ApplicationError("preset_not_found", "Saved task is unavailable", status=404)
            if isinstance(payload, TaskPresetCreate):
                package_key, workflow_key = payload.package_key, payload.workflow_key
            else:
                assert row is not None
                package_key, workflow_key = row.package_key, row.workflow_key
            lock_identity(session, "package:" + package_key)
            pointer = session.get(PackagePointerRow, package_key)
            if pointer is None:
                raise ApplicationError("package_not_found", "Task is unavailable", status=404)
            if pointer.package_hash != payload.package_hash:
                raise ApplicationError(
                    "preset_package_changed",
                    "Task changed; review and validate inputs again",
                    status=409,
                )
            revision = session.get(PackageRevisionRow, (package_key, pointer.package_hash))
            assert revision is not None
            workflow = revision.definition["workflows"].get(workflow_key)
            if workflow is None:
                raise ApplicationError("workflow_not_found", "Task is unavailable", status=404)
            if payload.has_parameters:
                validate_preset_parameters(workflow["inputSchema"], payload.parameters)
            now = datetime.now(UTC)
            if row is None:
                row = TaskPresetRow(
                    id=str(uuid4()),
                    package_key=package_key,
                    workflow_key=workflow_key,
                    created_at=now,
                )
                session.add(row)
            for key in ("name", "package_hash", "is_favorite", "is_pinned"):
                setattr(row, key, deepcopy(getattr(payload, key)))
            # Existing bookmarks use JSON null. SQL NULL preserves an explicitly
            # saved null input without changing the table or reinterpreting bookmarks.
            row.parameters = (
                null()
                if payload.has_parameters and payload.parameters is None
                else deepcopy(payload.parameters) if payload.has_parameters else JSONB.NULL
            )
            row.updated_at = now
            saved_id = row.id
        return self.get(saved_id)

    def delete(self, preset_id: str) -> None:
        with self.platform.session_factory() as session, session.begin():
            row = session.get(TaskPresetRow, preset_id, with_for_update=True)
            if row is None:
                raise ApplicationError("preset_not_found", "Saved task is unavailable", status=404)
            session.delete(row)

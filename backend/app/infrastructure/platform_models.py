"""Core platform tables with metadata independent of plugin-owned persistence."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.infrastructure.secret_storage import EncryptedJSONB


class PlatformBase(DeclarativeBase):
    pass


class PackageRevisionRow(PlatformBase):
    __tablename__ = "platform_package_revisions"
    package_key: Mapped[str] = mapped_column(String, primary_key=True)
    package_hash: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PackagePointerRow(PlatformBase):
    __tablename__ = "platform_packages"
    package_key: Mapped[str] = mapped_column(String, primary_key=True)
    package_hash: Mapped[str] = mapped_column(String)


class ResourceRow(PlatformBase):
    __tablename__ = "platform_resources"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    credentials: Mapped[dict[str, Any]] = mapped_column(EncryptedJSONB, deferred=True)
    has_credentials: Mapped[bool] = mapped_column(Boolean)
    credential_revision: Mapped[str] = mapped_column(String)


class PluginReleaseRow(PlatformBase):
    __tablename__ = "platform_plugin_releases"
    plugin_id: Mapped[str] = mapped_column(String, primary_key=True)
    artifact_digest: Mapped[str] = mapped_column(String, primary_key=True)
    descriptor: Mapped[dict[str, Any]] = mapped_column(JSONB)


class PluginPointerRow(PlatformBase):
    __tablename__ = "platform_plugins"
    plugin_id: Mapped[str] = mapped_column(String, primary_key=True)
    artifact_digest: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean)


class RunRow(PlatformBase):
    __tablename__ = "platform_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    launch_id: Mapped[str] = mapped_column(String, unique=True)
    launch_digest: Mapped[str] = mapped_column(String)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String)
    output: Mapped[Any] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommandRow(PlatformBase):
    __tablename__ = "platform_commands"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("platform_runs.id"))
    kind: Mapped[str] = mapped_column(String)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_code: Mapped[str | None] = mapped_column(String)


class EvidenceRow(PlatformBase):
    __tablename__ = "platform_evidence"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("platform_runs.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class OperationRow(PlatformBase):
    __tablename__ = "platform_tool_operations"
    id: Mapped[str] = mapped_column(ForeignKey("platform_evidence.id"), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

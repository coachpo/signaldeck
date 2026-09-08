"""PostgreSQL configuration revisions exposed as detached safe values."""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.execution import ApplicationError
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_models import (
    PackagePointerRow,
    PackageRevisionRow,
    PlatformBase,
    PluginPointerRow,
    PluginReleaseRow,
    ResourceRow,
)
from app.infrastructure.platform_run_store import PlatformRunStore
from app.infrastructure.platform_transactions import lock_identity


class PlatformStore(PlatformRunStore):
    def __init__(
        self, session_factory: sessionmaker[Session], artifacts: ArtifactStore | None = None
    ):
        self.session_factory = session_factory
        self.artifacts = artifacts

    def initialize(self) -> None:
        with self.session_factory() as session, session.begin():
            lock_identity(session, "platform-schema-initialization")
            PlatformBase.metadata.create_all(session.connection())

    def save_seed_package(
        self,
        package_key: str,
        source: str,
        definition: dict[str, Any],
        plan: dict[str, Any],
        package_hash: str,
    ) -> bool:
        """Install a missing seed atomically; an operator's package always wins."""
        with self.session_factory() as session, session.begin():
            lock_identity(session, "package:" + package_key)
            if session.get(PackagePointerRow, package_key) is not None:
                return False
            revision = session.get(PackageRevisionRow, (package_key, package_hash))
            if revision is not None:
                if (revision.source, revision.definition, revision.plan) != (
                    source,
                    definition,
                    plan,
                ):
                    raise ApplicationError(
                        "revision_conflict", "Immutable revision differs", status=409
                    )
            else:
                session.add(
                    PackageRevisionRow(
                        package_key=package_key,
                        package_hash=package_hash,
                        source=source,
                        definition=deepcopy(definition),
                        plan=deepcopy(plan),
                        created_at=datetime.now(UTC),
                    )
                )
            session.add(PackagePointerRow(package_key=package_key, package_hash=package_hash))
            return True

    def save_package(
        self,
        package_key: str,
        source: str,
        definition: dict[str, Any],
        plan: dict[str, Any],
        package_hash: str,
    ) -> dict[str, Any]:
        with self.session_factory() as session, session.begin():
            lock_identity(session, "package:" + package_key)
            revision = session.get(PackageRevisionRow, (package_key, package_hash))
            if revision is not None:
                if (
                    revision.source != source
                    or revision.definition != definition
                    or revision.plan != plan
                ):
                    raise ApplicationError(
                        "revision_conflict", "Immutable revision differs", status=409
                    )
            else:
                session.add(
                    PackageRevisionRow(
                        package_key=package_key,
                        package_hash=package_hash,
                        source=source,
                        definition=deepcopy(definition),
                        plan=deepcopy(plan),
                        created_at=datetime.now(UTC),
                    )
                )
            pointer = session.get(PackagePointerRow, package_key)
            if pointer is None:
                session.add(PackagePointerRow(package_key=package_key, package_hash=package_hash))
            else:
                pointer.package_hash = package_hash
        result = self.get_package(package_key, package_hash)
        assert result is not None
        return result

    def get_package(
        self, package_key: str, revision_hash: str | None = None
    ) -> dict[str, Any] | None:
        with self.session_factory() as session:
            if revision_hash is None:
                pointer = session.get(PackagePointerRow, package_key)
                if pointer is None:
                    return None
                revision_hash = pointer.package_hash
            row = session.get(PackageRevisionRow, (package_key, revision_hash))
            return None if row is None else self._package_value(row)

    @staticmethod
    def _package_value(row: PackageRevisionRow) -> dict[str, Any]:
        return {
            "packageKey": row.package_key,
            "packageHash": row.package_hash,
            "source": row.source,
            "definition": deepcopy(row.definition),
            "plan": deepcopy(row.plan),
            "createdAt": row.created_at.isoformat(),
        }

    def list_packages(self) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(PackageRevisionRow)
                .join(
                    PackagePointerRow,
                    (PackageRevisionRow.package_key == PackagePointerRow.package_key)
                    & (PackageRevisionRow.package_hash == PackagePointerRow.package_hash),
                )
                .order_by(PackageRevisionRow.package_key)
            ).all()
            return [self._package_value(row) for row in rows]

    def save_resource(
        self,
        resource_id: str,
        kind: str,
        config: dict[str, Any],
        credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.session_factory() as session, session.begin():
            lock_identity(session, "resource:" + resource_id)
            row = session.get(ResourceRow, resource_id)
            if row is None:
                row = ResourceRow(
                    id=resource_id,
                    kind=kind,
                    config=deepcopy(config),
                    credentials=credentials or {},
                    has_credentials=bool(credentials),
                    credential_revision=str(uuid4()),
                )
                session.add(row)
            else:
                row.kind, row.config = kind, deepcopy(config)
                if credentials is not None:
                    row.credentials, row.has_credentials = deepcopy(credentials), bool(credentials)
                    row.credential_revision = str(uuid4())
        result = self.get_resource(resource_id)
        assert result is not None
        return result

    def get_resource(self, resource_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.execute(
                select(
                    ResourceRow.id,
                    ResourceRow.kind,
                    ResourceRow.config,
                    ResourceRow.has_credentials,
                    ResourceRow.credential_revision,
                ).where(ResourceRow.id == resource_id)
            ).first()
            return (
                None
                if row is None
                else {
                    "id": row.id,
                    "kind": row.kind,
                    "config": deepcopy(row.config),
                    "hasCredentials": row.has_credentials,
                    "credentialRevision": row.credential_revision,
                }
            )

    def list_resources(self, kind: str | None = None) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            query = select(
                ResourceRow.id,
                ResourceRow.kind,
                ResourceRow.config,
                ResourceRow.has_credentials,
                ResourceRow.credential_revision,
            )
            if kind is not None:
                query = query.where(ResourceRow.kind == kind)
            return [
                {
                    "id": row.id,
                    "kind": row.kind,
                    "config": deepcopy(row.config),
                    "hasCredentials": row.has_credentials,
                    "credentialRevision": row.credential_revision,
                }
                for row in session.execute(query.order_by(ResourceRow.id))
            ]

    def resolve_credentials(self, resource_id: str) -> dict[str, Any]:
        """I/O adapters alone may call this explicit decryption boundary."""
        with self.session_factory() as session:
            value = session.scalar(
                select(ResourceRow.credentials).where(ResourceRow.id == resource_id)
            )
            if value is None:
                raise ApplicationError("resource_not_found", "Resource is unavailable", status=404)
            return deepcopy(value)

    def resolve_bound_credentials(self, resource_id: str, expected_revision: str) -> dict[str, Any]:
        """Resolve one pinned secret reference without accepting a rotated identity."""
        with self.session_factory() as session, session.begin():
            revision = session.scalar(
                select(ResourceRow.credential_revision)
                .where(ResourceRow.id == resource_id)
                .with_for_update(read=True)
            )
            if revision is None:
                raise ApplicationError("resource_not_found", "Resource is unavailable", status=404)
            if revision != expected_revision:
                raise ApplicationError(
                    "resource_binding_changed",
                    "The bound credential revision is unavailable",
                    status=409,
                )
            value = session.scalar(
                select(ResourceRow.credentials).where(ResourceRow.id == resource_id)
            )
            if value is None:
                raise ApplicationError("resource_not_found", "Resource is unavailable", status=404)
            return deepcopy(value)

    def install_plugin(
        self, plugin_id: str, release: dict[str, Any], enabled: bool = True
    ) -> dict[str, Any]:
        digest = str(release["artifactDigest"])
        with self.session_factory() as session, session.begin():
            lock_identity(session, "plugin:" + plugin_id)
            row = session.get(PluginReleaseRow, (plugin_id, digest))
            if row is not None and row.descriptor != release:
                raise ApplicationError(
                    "release_conflict", "Immutable plugin release differs", status=409
                )
            if row is None:
                session.add(
                    PluginReleaseRow(
                        plugin_id=plugin_id, artifact_digest=digest, descriptor=deepcopy(release)
                    )
                )
            pointer = session.get(PluginPointerRow, plugin_id)
            if pointer is None:
                session.add(
                    PluginPointerRow(plugin_id=plugin_id, artifact_digest=digest, enabled=enabled)
                )
            else:
                pointer.artifact_digest, pointer.enabled = digest, enabled
        return {"pluginId": plugin_id, "enabled": enabled, "release": deepcopy(release)}

    def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        with self.session_factory() as session, session.begin():
            lock_identity(session, "plugin:" + plugin_id)
            row = session.get(PluginPointerRow, plugin_id)
            if row is None:
                raise ApplicationError("plugin_not_found", "Plugin is not installed", status=404)
            row.enabled = enabled
            release = session.get(PluginReleaseRow, (plugin_id, row.artifact_digest))
            assert release is not None
            return {
                "pluginId": plugin_id,
                "enabled": enabled,
                "release": deepcopy(release.descriptor),
            }

    def list_plugins(self) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.execute(
                select(PluginPointerRow, PluginReleaseRow)
                .join(
                    PluginReleaseRow,
                    (PluginPointerRow.plugin_id == PluginReleaseRow.plugin_id)
                    & (PluginPointerRow.artifact_digest == PluginReleaseRow.artifact_digest),
                )
                .order_by(PluginPointerRow.plugin_id)
            )
            return [
                {
                    "pluginId": pointer.plugin_id,
                    "enabled": pointer.enabled,
                    "release": deepcopy(release.descriptor),
                }
                for pointer, release in rows
            ]

    def get_plugin_release(self, plugin_id: str, artifact_digest: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.get(PluginReleaseRow, (plugin_id, artifact_digest))
            return None if row is None else deepcopy(row.descriptor)

"""API composition of explicit application and persistence adapters."""

from pathlib import Path

from fastapi import Request

from app.application.launch import LaunchService
from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.core_artifacts import CoreArtifactStore
from app.infrastructure.platform_store import PlatformStore


def get_artifacts() -> ArtifactStore:
    return ArtifactStore(Path(get_settings().artifact_dir))


def get_platform_store() -> PlatformStore:
    # API commands do not record execution outputs. Historical queries need only
    # PostgreSQL; the artifact volume is opened by downloads or execution adapters.
    return PlatformStore(get_session_factory())


def get_core_artifacts() -> CoreArtifactStore:
    return CoreArtifactStore(
        Path(get_settings().core_artifact_dir),
        source_root=Path(__file__).resolve().parents[2],
    )


class PublishedCore:
    def __init__(self, digest: str) -> None:
        self.digest = digest

    def current_digest(self) -> str:
        return self.digest


def get_published_core(request: Request) -> PublishedCore:
    digest = getattr(request.app.state, "core_artifact_digest", None)
    if digest is None:
        digest = get_core_artifacts().current_digest()
        request.app.state.core_artifact_digest = digest
    return PublishedCore(digest)


def get_launch_service(request: Request) -> LaunchService:
    return LaunchService(get_platform_store(), get_published_core(request))

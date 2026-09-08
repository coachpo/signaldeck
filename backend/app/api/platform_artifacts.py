"""Download verified immutable content without resolving live plugin state."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.platform_dependencies import get_artifacts
from app.domain.execution import ApplicationError
from app.infrastructure.artifact_store import ArtifactIntegrityError, ArtifactStore

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{digest}")
def download_artifact(
    digest: str, artifacts: Annotated[ArtifactStore, Depends(get_artifacts)]
) -> Response:
    try:
        content = artifacts.read(artifacts.inspect(digest))
    except (ArtifactIntegrityError, ValueError) as exc:
        raise ApplicationError(
            "artifact_unavailable", "Artifact is unavailable", status=404
        ) from exc
    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{digest.removeprefix("sha256:")}"',
            "X-Content-Type-Options": "nosniff",
            "ETag": f'"{digest}"',
        },
    )

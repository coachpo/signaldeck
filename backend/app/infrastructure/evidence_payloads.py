"""Content-addressed JSON values at execution evidence persistence boundaries."""

from copy import deepcopy
from typing import Any

from app.domain.tool_contracts import ArtifactRef
from app.infrastructure.artifact_store import ArtifactIntegrityError, ArtifactStore


def artifact_reference(value: Any) -> ArtifactRef | None:
    if isinstance(value, dict) and set(value) == {"$artifact"}:
        return ArtifactRef.model_validate(value["$artifact"])
    return None


def persist_value(value: Any, artifacts: ArtifactStore | None) -> Any:
    """Preserve an existing reference; large values become one immutable reference."""
    existing = artifact_reference(value)
    if existing is not None:
        return {"$artifact": existing.model_dump(mode="json", by_alias=True)}
    if artifacts is None:
        return deepcopy(value)
    stored = artifacts.store_json(value)
    if isinstance(stored, ArtifactRef):
        return {"$artifact": stored.model_dump(mode="json", by_alias=True)}
    return stored


def execution_value(value: Any, artifacts: ArtifactStore | None) -> Any:
    """Only execution consumers inflate objects; browser projections retain references."""
    ref = artifact_reference(value)
    if ref is None:
        return deepcopy(value)
    if artifacts is None:
        raise ArtifactIntegrityError("Artifact storage is required for execution recovery")
    return artifacts.read_json(ref)

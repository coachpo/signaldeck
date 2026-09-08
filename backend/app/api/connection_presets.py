"""Expose only operator-declared connection defaults, without probing services."""

import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import ValidationError

from app.domain.execution import ApplicationError
from app.schemas.connection_presets import ConnectionPresetList

router = APIRouter(prefix="/connection-presets", tags=["resources"])


@router.get("", response_model=ConnectionPresetList)
def connection_presets() -> ConnectionPresetList:
    path = os.environ.get("SIGNALDECK_CONNECTION_PRESETS_FILE")
    if not path:
        return ConnectionPresetList()
    try:
        return ConnectionPresetList.model_validate_json(Path(path).read_bytes())
    except (OSError, ValueError, ValidationError) as exc:
        raise ApplicationError(
            "connection_presets_unavailable", "Connection choices are unavailable", status=503
        ) from exc

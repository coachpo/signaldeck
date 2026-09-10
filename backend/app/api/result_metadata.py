"""Explicit personal annotation commands and read-only annotation retrieval."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.platform_dependencies import get_platform_store
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.result_metadata_store import ResultMetadataStore
from app.schemas.result_metadata import ResultMetadataPatch, ResultMetadataRead

router = APIRouter(prefix="/runs", tags=["result-metadata"])
Store = Annotated[PlatformStore, Depends(get_platform_store)]


@router.get("/{run_id}/metadata", response_model=ResultMetadataRead)
def get_metadata(run_id: str, store: Store) -> ResultMetadataRead:
    return ResultMetadataStore(store).get(run_id)


@router.patch("/{run_id}/metadata", response_model=ResultMetadataRead)
def patch_metadata(run_id: str, payload: ResultMetadataPatch, store: Store) -> ResultMetadataRead:
    return ResultMetadataStore(store).patch(run_id, payload)

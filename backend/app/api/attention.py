"""Execution update reads and explicit read receipts; no engine dependency."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.platform_dependencies import get_platform_store
from app.infrastructure.attention_store import AttentionStore
from app.infrastructure.platform_store import PlatformStore
from app.schemas.attention import AttentionItem, AttentionList, AttentionReadPatch

router = APIRouter(prefix="/attention", tags=["attention"])
Store = Annotated[PlatformStore, Depends(get_platform_store)]


@router.get("", response_model=AttentionList)
def list_attention(
    store: Store,
    view: Literal["all", "attention"] = "attention",
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    snapshot_at: datetime | None = Query(default=None, alias="snapshotAt"),
) -> AttentionList:
    return AttentionStore(store).list(
        view=view, limit=limit, offset=offset, snapshot_at=snapshot_at
    )


@router.patch("/{identity}", response_model=AttentionItem)
def mark_attention(identity: str, payload: AttentionReadPatch, store: Store) -> AttentionItem:
    return AttentionStore(store).mark(identity, payload)

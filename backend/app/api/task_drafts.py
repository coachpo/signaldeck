"""Explicit draft writes never launch or schedule work."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.platform_dependencies import get_platform_store
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.task_draft_store import TaskDraftStore
from app.schemas.task_drafts import TaskDraftList, TaskDraftRead, TaskDraftWrite

router = APIRouter(prefix="/task-drafts", tags=["task-drafts"])


def get_task_draft_store(
    platform: Annotated[PlatformStore, Depends(get_platform_store)],
) -> TaskDraftStore:
    return TaskDraftStore(platform)


Store = Annotated[TaskDraftStore, Depends(get_task_draft_store)]


@router.get("", response_model=TaskDraftList)
def list_drafts(store: Store) -> TaskDraftList:
    return TaskDraftList(items=store.list())


@router.get("/{identity}", response_model=TaskDraftRead)
def get_draft(identity: str, store: Store) -> TaskDraftRead:
    return store.get(identity)


@router.put("/{identity}", response_model=TaskDraftRead)
def save_draft(identity: str, payload: TaskDraftWrite, store: Store) -> TaskDraftRead:
    return store.save(identity, payload)


@router.delete("/{identity}", status_code=204)
def delete_draft(identity: str, store: Store, revision: Annotated[int, Query(ge=1)]) -> Response:
    store.delete(identity, revision)
    return Response(status_code=204)

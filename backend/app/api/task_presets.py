"""Saved business inputs and bookmarks, independent of launch and schedule effects."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.platform_dependencies import get_platform_store
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.task_preset_store import TaskPresetStore
from app.schemas.task_presets import (
    TaskPresetCreate,
    TaskPresetList,
    TaskPresetRead,
    TaskPresetUpdate,
)

router = APIRouter(prefix="/task-presets", tags=["task-presets"])


def get_task_preset_store(
    platform: Annotated[PlatformStore, Depends(get_platform_store)],
) -> TaskPresetStore:
    return TaskPresetStore(platform)


Store = Annotated[TaskPresetStore, Depends(get_task_preset_store)]


@router.get("", response_model=TaskPresetList)
def list_presets(store: Store) -> TaskPresetList:
    return TaskPresetList(items=store.list())


@router.post("", response_model=TaskPresetRead, status_code=201)
def create_preset(payload: TaskPresetCreate, store: Store) -> TaskPresetRead:
    return store.save(payload)


@router.get("/{preset_id}", response_model=TaskPresetRead)
def get_preset(preset_id: str, store: Store) -> TaskPresetRead:
    return store.get(preset_id)


@router.put("/{preset_id}", response_model=TaskPresetRead)
def update_preset(preset_id: str, payload: TaskPresetUpdate, store: Store) -> TaskPresetRead:
    return store.save(payload, preset_id)


@router.delete("/{preset_id}", status_code=204)
def delete_preset(preset_id: str, store: Store) -> Response:
    store.delete(preset_id)
    return Response(status_code=204)

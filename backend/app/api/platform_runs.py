"""Historical run reads and durable operator commands."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.platform_dependencies import get_launch_service, get_platform_store
from app.application.launch import LaunchService
from app.domain.execution import ApplicationError, LaunchOrigin, RunDetail, RunSummary
from app.infrastructure.platform_store import PlatformStore
from app.schemas.common import CamelModel
from app.schemas.platform import RerunRequest

router = APIRouter(prefix="/runs", tags=["runs"])
Store = Annotated[PlatformStore, Depends(get_platform_store)]


class RunList(CamelModel):
    items: list[RunSummary]


@router.get("", response_model=RunList)
def list_runs(store: Store) -> RunList:
    return RunList(items=store.list_runs())


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, store: Store) -> RunDetail:
    result = store.get_run(run_id)
    if result is None:
        raise ApplicationError("run_not_found", "Run is unavailable", status=404)
    return result


@router.post("/{run_id}/cancel", response_model=RunSummary)
def cancel_run(run_id: str, store: Store) -> RunSummary:
    return store.request_cancel(run_id)


@router.post("/{run_id}/rerun", response_model=RunSummary, status_code=201)
def rerun(
    run_id: str,
    payload: RerunRequest,
    store: Store,
    service: Annotated[LaunchService, Depends(get_launch_service)],
) -> RunSummary:
    original = get_run(run_id, store)
    return service.launch(
        original.package_key,
        original.workflow_key,
        original.spec.parameters,
        launch_id=payload.launch_id,
        origin=LaunchOrigin(kind="rerun", source_run_id=run_id),
        revision_hash=original.package_hash,
    )

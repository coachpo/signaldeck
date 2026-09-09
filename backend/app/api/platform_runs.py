"""Historical run reads and durable operator commands."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.platform_dependencies import get_launch_service, get_platform_store
from app.application.launch import LaunchService
from app.application.result_projection import project_result
from app.domain.definitions import PackageDefinition
from app.domain.execution import ApplicationError, LaunchOrigin, RunDetail, RunSummary
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.run_history import query_history
from app.schemas.common import CamelModel
from app.schemas.platform import RerunRequest
from app.schemas.task_experience import ResultRead, ReuseRead, ReuseRequest

router = APIRouter(prefix="/runs", tags=["runs"])
Store = Annotated[PlatformStore, Depends(get_platform_store)]


class RunList(CamelModel):
    items: list[RunSummary]
    total: int
    limit: int
    offset: int
    snapshot_at: datetime


@router.get("", response_model=RunList)
def list_runs(
    store: Store,
    q: str | None = Query(default=None, max_length=500),
    group: Literal["active", "attention"] | None = None,
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] | None = None,
    package_key: str | None = Query(default=None, alias="packageKey"),
    workflow_key: str | None = Query(default=None, alias="workflowKey"),
    origin: Literal["manual", "rerun", "reuse", "schedule"] | None = None,
    created_from: datetime | None = Query(default=None, alias="createdFrom"),
    created_to: datetime | None = Query(default=None, alias="createdTo"),
    sort: Literal["created_desc", "created_asc", "title_asc", "title_desc"] = "created_desc",
    snapshot_at: datetime | None = Query(default=None, alias="snapshotAt"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RunList:
    snapshot_at = snapshot_at or datetime.now(UTC)
    snapshot_at = snapshot_at.replace(tzinfo=UTC) if snapshot_at.tzinfo is None else snapshot_at
    if created_to is not None and created_to.tzinfo is None:
        created_to = created_to.replace(tzinfo=UTC)
    rows, total, unknown_ids = query_history(
        store.session_factory,
        q=q,
        group=group,
        status=status,
        package_key=package_key,
        workflow_key=workflow_key,
        origin=origin,
        created_from=created_from,
        created_to=min(created_to, snapshot_at) if created_to else snapshot_at,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return RunList(
        items=[
            store._summary(row).model_copy(update={"has_unknown_effects": row.id in unknown_ids})
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
        snapshot_at=snapshot_at,
    )


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
        binding_token=payload.binding_token,
    )


@router.get("/{run_id}/result", response_model=ResultRead)
def get_result(run_id: str, store: Store) -> ResultRead:
    return project_result(get_run(run_id, store))


@router.get("/{run_id}/reuse", response_model=ReuseRead)
def reuse_input(run_id: str, store: Store) -> ReuseRead:
    original = get_run(run_id, store)
    workflow = PackageDefinition.model_validate(original.spec.definition).workflows[
        original.workflow_key
    ]
    return ReuseRead(
        source_run_id=run_id,
        package_key=original.package_key,
        workflow_key=original.workflow_key,
        package_hash=original.package_hash,
        parameters=original.spec.parameters,
        input_schema=workflow.input_schema,
        workflow=workflow,
    )


@router.post("/{run_id}/reuse", response_model=RunSummary, status_code=201)
def launch_reused_input(
    run_id: str,
    payload: ReuseRequest,
    store: Store,
    service: Annotated[LaunchService, Depends(get_launch_service)],
) -> RunSummary:
    original = get_run(run_id, store)
    return service.launch(
        original.package_key,
        original.workflow_key,
        payload.parameters,
        launch_id=payload.launch_id,
        origin=LaunchOrigin(kind="reuse", source_run_id=run_id),
        revision_hash=original.package_hash,
        binding_token=payload.binding_token,
    )

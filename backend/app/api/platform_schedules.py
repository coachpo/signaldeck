"""Schedule configuration endpoints; Temporal alone evaluates firing policies."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field

from app.api.platform_dependencies import get_artifacts, get_platform_store, get_published_core
from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.domain.compiler import compile_package
from app.domain.execution import ApplicationError
from app.domain.schedules import (
    ScheduleDefinition,
    ScheduleFireRecord,
    ScheduleRecord,
    ScheduleTriggerReceipt,
)
from app.domain.schema_contract import validate_value
from app.infrastructure.core_artifacts import task_queue
from app.infrastructure.schedule_store import ScheduleStore
from app.infrastructure.temporal_client import connect_client
from app.infrastructure.temporal_schedules import TemporalScheduleService
from app.schemas.common import CamelModel

router = APIRouter(prefix="/schedules", tags=["schedules"])


class ScheduleList(CamelModel):
    items: list[ScheduleRecord]


class FireList(CamelModel):
    items: list[ScheduleFireRecord]


class TriggerRequest(CamelModel):
    trigger_id: str = Field(min_length=1, max_length=200)


def get_schedule_store() -> ScheduleStore:
    return ScheduleStore(get_session_factory())


async def get_schedule_service(request: Request) -> TemporalScheduleService:
    client = getattr(request.app.state, "temporal_client", None)
    if client is None:
        try:
            async with asyncio.timeout(10):
                client = await connect_client(get_settings().temporal_address, get_artifacts())
            request.app.state.temporal_client = client
        except Exception as exc:
            raise ApplicationError(
                "engine_unavailable", "Execution engine is unavailable", status=503
            ) from exc
    return TemporalScheduleService(
        client, get_schedule_store(), task_queue(get_published_core(request).current_digest())
    )


Store = Annotated[ScheduleStore, Depends(get_schedule_store)]
Service = Annotated[TemporalScheduleService, Depends(get_schedule_service)]


def _validate_definition(payload: ScheduleDefinition) -> None:
    package = get_platform_store().get_package(payload.package_key)
    if package is None:
        raise ApplicationError("package_not_found", "Workflow Package is unavailable", status=404)
    compiled = compile_package(package["definition"])
    workflow = compiled.package.workflows.get(payload.workflow_key)
    if workflow is None:
        raise ApplicationError("workflow_not_found", "Workflow is unavailable", status=404)
    validate_value(workflow.input_schema, payload.parameters, "$.parameters")


@router.get("", response_model=ScheduleList)
def list_schedules(store: Store) -> ScheduleList:
    return ScheduleList(items=store.list())


@router.post("", response_model=ScheduleRecord, status_code=201)
async def create_schedule(payload: ScheduleDefinition, service: Service) -> ScheduleRecord:
    _validate_definition(payload)
    return await service.save(payload)


@router.get("/{schedule_id}", response_model=ScheduleRecord)
def get_schedule(schedule_id: str, store: Store) -> ScheduleRecord:
    record = store.get(schedule_id)
    if record is None or record.sync_status == "deleted":
        raise ApplicationError("schedule_not_found", "Schedule is unavailable", status=404)
    return record


@router.patch("/{schedule_id}", response_model=ScheduleRecord)
async def update_schedule(
    schedule_id: str, payload: ScheduleDefinition, service: Service
) -> ScheduleRecord:
    _validate_definition(payload)
    return await service.save(payload, schedule_id)


@router.get("/{schedule_id}/fires", response_model=FireList)
def list_schedule_fires(schedule_id: str, store: Store) -> FireList:
    # Deleted configuration retains its immutable run/fire provenance.
    if store.get(schedule_id) is None:
        raise ApplicationError("schedule_not_found", "Schedule is unavailable", status=404)
    return FireList(items=store.list_fires(schedule_id))


@router.delete("/{schedule_id}", status_code=204, response_model=None)
async def delete_schedule(schedule_id: str, service: Service) -> Response:
    await service.delete(schedule_id)
    return Response(status_code=204)


@router.post("/{schedule_id}/trigger", response_model=ScheduleTriggerReceipt)
async def trigger_schedule(
    schedule_id: str, payload: TriggerRequest, service: Service
) -> ScheduleTriggerReceipt:
    return await service.trigger(schedule_id, payload.trigger_id)

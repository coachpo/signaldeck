"""Calendar previews delegated to Temporal without launching application work."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleState
from temporalio.service import RPCError, RPCStatusCode

from app.domain.execution import ApplicationError
from app.domain.schedules import ScheduleCalendar, SchedulePreview
from app.infrastructure.temporal_schedules import TemporalScheduleService, engine_schedule_id


async def preview_calendar(
    service: TemporalScheduleService,
    calendar: ScheduleCalendar,
    *,
    start_at: datetime | None = None,
) -> SchedulePreview:
    # A paused, input-free schedule lets the installed server interpret cron and DST.
    # It never targets an executable workflow and is removed even if describe fails.
    identity = "signaldeck-preview:" + str(uuid4())
    handle = service.client.get_schedule_handle(identity)
    try:
        await service.client.create_schedule(
            identity,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    "SignalDeckCalendarPreview", id=identity, task_queue=identity
                ),
                spec=ScheduleSpec(
                    cron_expressions=[calendar.cron],
                    time_zone_name=calendar.time_zone,
                    start_at=start_at,
                ),
                state=ScheduleState(paused=True),
            ),
            rpc_timeout=timedelta(seconds=10),
        )
        description = await handle.describe(rpc_timeout=timedelta(seconds=10))
        return SchedulePreview(
            time_zone=calendar.time_zone,
            times=list(description.info.next_action_times)[:5],
            observed_at=datetime.now(UTC),
            scope="draft",
        )
    finally:
        try:
            await handle.delete(rpc_timeout=timedelta(seconds=10))
        except RPCError as exc:
            if exc.status != RPCStatusCode.NOT_FOUND:
                raise


async def preview_saved(service: TemporalScheduleService, schedule_id: str) -> SchedulePreview:
    record = service.store.get(schedule_id)
    if record is None or record.desired_deleted:
        raise ApplicationError("schedule_not_found", "Schedule is unavailable", status=404)
    description = await service.client.get_schedule_handle(
        engine_schedule_id(schedule_id)
    ).describe(rpc_timeout=timedelta(seconds=10))
    return SchedulePreview(
        time_zone=description.schedule.spec.time_zone_name or "UTC",
        times=list(description.info.next_action_times)[:5],
        observed_at=datetime.now(UTC),
        scope="applied",
        desired_revision=record.revision,
        synced_revision=record.synced_revision,
        applied_note=description.schedule.state.note,
        paused=description.schedule.state.paused,
    )

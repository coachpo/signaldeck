"""Reconcile desired configuration with Temporal's calendar and overlap authority."""

from datetime import UTC, datetime, timedelta

from google.protobuf.timestamp_pb2 import Timestamp
from temporalio.api.schedule.v1 import SchedulePatch, TriggerImmediatelyRequest
from temporalio.api.workflowservice.v1 import PatchScheduleRequest
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    ScheduleState,
    ScheduleUpdate,
    WorkflowExecutionStatus,
)
from temporalio.service import RPCError, RPCStatusCode

from app.domain.execution import ApplicationError
from app.domain.schedules import ScheduleDefinition, ScheduleRecord, ScheduleTriggerReceipt
from app.domain.tool_contracts import canonical_digest
from app.infrastructure.schedule_store import ScheduleStore
from app.infrastructure.temporal_projection import TemporalExecutionObserver

_OVERLAP = {
    "skip": ScheduleOverlapPolicy.SKIP,
    "buffer_one": ScheduleOverlapPolicy.BUFFER_ONE,
    "allow": ScheduleOverlapPolicy.ALLOW_ALL,
}


def engine_schedule_id(schedule_id: str) -> str:
    return "signaldeck-schedule:" + schedule_id


def _failure(exc: Exception) -> ApplicationError:
    if isinstance(exc, RPCError) and exc.status == RPCStatusCode.INVALID_ARGUMENT:
        return ApplicationError("schedule_invalid", "The engine rejected this schedule", status=422)
    return ApplicationError("schedule_sync_failed", "Schedule synchronization failed", status=503)


class TemporalScheduleService:
    def __init__(self, client: Client, store: ScheduleStore, task_queue: str) -> None:
        self.client, self.store, self.task_queue = client, store, task_queue

    async def save(
        self,
        definition: ScheduleDefinition,
        schedule_id: str | None = None,
        *,
        create_only: bool = False,
    ) -> ScheduleRecord:
        record = self.store.save(definition, schedule_id, create_only=create_only)
        return await self.store.synchronize(record.id, self._apply)

    async def delete(self, schedule_id: str) -> None:
        self.store.mark_deleted(schedule_id)
        await self.store.synchronize(schedule_id, self._apply)

    def _schedule(self, record: ScheduleRecord) -> Schedule:
        definition = ScheduleDefinition.model_validate(
            {key: getattr(record, key) for key in ScheduleDefinition.model_fields}
        )
        return Schedule(
            action=ScheduleActionStartWorkflow(
                "ScheduleFireWorkflow",
                {
                    "scheduleId": record.id,
                    "definition": definition.model_dump(mode="json", by_alias=True),
                },
                id="signaldeck-fire:" + record.id,
                task_queue=self.task_queue,
            ),
            spec=ScheduleSpec(
                cron_expressions=[record.cron],
                time_zone_name=record.time_zone,
                # Automatic and backfill matches cannot enter the manual identity range.
                start_at=datetime(1970, 1, 1, tzinfo=UTC),
            ),
            policy=SchedulePolicy(
                overlap=_OVERLAP[record.overlap_policy],
                catchup_window=timedelta(seconds=record.catchup_window_seconds),
            ),
            state=ScheduleState(
                paused=record.paused, note=f"SignalDeck revision {record.revision}"
            ),
        )

    async def _apply(self, record: ScheduleRecord) -> None:
        identity = engine_schedule_id(record.id)
        handle = self.client.get_schedule_handle(identity)
        try:
            if record.desired_deleted:
                try:
                    await handle.delete(rpc_timeout=timedelta(seconds=10))
                except RPCError as exc:
                    if exc.status != RPCStatusCode.NOT_FOUND:
                        raise
                return
            desired = self._schedule(record)
            try:
                await self.client.create_schedule(
                    identity, desired, rpc_timeout=timedelta(seconds=10)
                )
            except ScheduleAlreadyRunningError:
                await handle.update(
                    lambda _: ScheduleUpdate(schedule=desired), rpc_timeout=timedelta(seconds=10)
                )
        except Exception as exc:
            raise _failure(exc) from None

    async def trigger(self, schedule_id: str, trigger_id: str) -> ScheduleTriggerReceipt:
        if not trigger_id.strip() or len(trigger_id) > 200:
            raise ApplicationError("trigger_identity_invalid", "A trigger identity is required")
        receipt = self.store.request_trigger(schedule_id, trigger_id)
        if receipt.status == "accepted":
            return receipt
        await self.store.synchronize(schedule_id, self._apply)
        return await self._deliver_trigger(schedule_id, trigger_id)

    async def _deliver_trigger(self, schedule_id: str, trigger_id: str) -> ScheduleTriggerReceipt:
        async def send(identity_time: datetime) -> None:
            request_id = canonical_digest({"scheduleId": schedule_id, "triggerId": trigger_id})
            identity_timestamp = Timestamp()
            identity_timestamp.FromDatetime(identity_time)
            try:
                # The public helper generates a fresh request ID each time. The wire protocol
                # exposes this stable ID so a lost response can be retried without another fire.
                await self.client.workflow_service.patch_schedule(
                    PatchScheduleRequest(
                        namespace=self.client.namespace,
                        schedule_id=engine_schedule_id(schedule_id),
                        identity="signaldeck-command-dispatcher",
                        request_id=request_id,
                        patch=SchedulePatch(
                            trigger_immediately=TriggerImmediatelyRequest(
                                scheduled_time=identity_timestamp
                            )
                        ),
                    ),
                    retry=True,
                    timeout=timedelta(seconds=10),
                )
            except Exception as exc:
                raise _failure(exc) from None

        return await self.store.deliver_trigger(schedule_id, trigger_id, send)

    async def reconcile(self) -> dict[str, int]:
        synchronized, failed = 0, 0
        for record in self.store.pending():
            try:
                await self.store.synchronize(record.id, self._apply)
                synchronized += 1
            except ApplicationError:
                failed += 1
        for trigger in self.store.pending_triggers():
            try:
                await self._deliver_trigger(trigger.schedule_id, trigger.trigger_id)
                synchronized += 1
            except ApplicationError:
                failed += 1
        return {"synchronized": synchronized, "failed": failed}

    async def project_fires(self) -> dict[str, int]:
        """Consume engine/admission facts; never start, cancel, or reschedule work."""
        counts = {"examined": 0, "projected": 0, "unavailable": 0}
        observer = TemporalExecutionObserver(self.client)
        for fire in self.store.fires.unfinished():
            counts["examined"] += 1
            try:
                run_id = fire.run_id or self.store.fires.launched_run(fire.trigger_id)
                if run_id is not None:
                    if fire.run_id is None:
                        self.store.fires.launched(fire.trigger_id, run_id)
                    rejection = self.store.fires.admission_failure(run_id)
                    if rejection:
                        self.store.fires.finished(run_id, "failed", rejection)
                        counts["projected"] += 1
                        continue
                    fact = await observer.terminal_fact(run_id)
                    if fact is not None:
                        self.store.fires.finished(run_id, fact.status, fact.error_code)
                        counts["projected"] += 1
                    continue
                execution = await self.client.get_workflow_handle(
                    fire.engine_workflow_id, run_id=fire.engine_run_id
                ).describe(rpc_timeout=timedelta(seconds=5))
                if execution.close_time is None:
                    continue
                code = (
                    "schedule_launch_timed_out"
                    if execution.status == WorkflowExecutionStatus.TIMED_OUT
                    else (
                        "schedule_launch_cancelled"
                        if execution.status == WorkflowExecutionStatus.CANCELED
                        else "schedule_launch_failed"
                    )
                )
                counts["projected"] += int(
                    self.store.fires.project_launch_failure(fire.trigger_id, code)
                )
            except Exception:
                counts["unavailable"] += 1
        return counts

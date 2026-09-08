"""Keep each engine Schedule action open for the entire launched Run lifecycle."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import activity, workflow
from temporalio.client import WorkflowFailureError
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError as TemporalApplicationError

with workflow.unsafe.imports_passed_through():
    from pydantic import ValidationError

    from app.application.dispatch import AdmissionRejected, CommandDispatcher
    from app.application.launch import LaunchService
    from app.domain.execution import ApplicationError, LaunchOrigin
    from app.domain.schedules import ScheduleFireRecord
    from app.domain.schema_contract import DomainValidationError
    from app.domain.tool_contracts import canonical_digest
    from app.infrastructure.platform_store import PlatformStore
    from app.infrastructure.schedule_store import ScheduleStore
    from app.infrastructure.temporal_dispatch import TemporalRunEngine
    from app.infrastructure.temporal_projection import TemporalExecutionObserver


@workflow.defn
class ScheduleFireWorkflow:
    @workflow.run
    async def run(self, command: dict[str, Any]) -> dict[str, str]:
        info = workflow.info()
        scheduled_times = info.search_attributes.get("TemporalScheduledStartTime", [])
        scheduled_at = scheduled_times[0] if scheduled_times else info.start_time
        assert isinstance(scheduled_at, datetime)
        # A logical fire survives a new wrapper execution after response loss or reset.
        # Manual identities occupy a ledger-owned range disjoint from calendar matches.
        trigger_id = canonical_digest(
            {"scheduleId": command["scheduleId"], "identityTime": scheduled_at.isoformat()}
        )
        launch = await workflow.execute_activity(
            "launch_schedule_fire",
            {
                **command,
                "triggerId": trigger_id,
                "scheduledAt": scheduled_at.isoformat(),
                "engineWorkflowId": info.workflow_id,
                "engineRunId": info.first_execution_run_id,
            },
            start_to_close_timeout=timedelta(seconds=30),
            schedule_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=10)
            ),
        )
        deadline = datetime.fromisoformat(launch["deadline"].replace("Z", "+00:00"))
        remaining = max((deadline - workflow.now()).total_seconds(), 0)
        await workflow.execute_activity(
            "wait_scheduled_run",
            launch["runId"],
            start_to_close_timeout=timedelta(seconds=remaining + 120),
            heartbeat_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=10)
            ),
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )
        return {"runId": launch["runId"], "triggerId": trigger_id}


class TemporalScheduleActivities:
    def __init__(
        self,
        launch_service: LaunchService,
        store: PlatformStore,
        engine: TemporalRunEngine,
        schedules: ScheduleStore,
    ) -> None:
        self.launch_service, self.store, self.engine = launch_service, store, engine
        self.schedules = schedules

    @activity.defn(name="launch_schedule_fire")
    async def launch_fire(self, command: dict[str, Any]) -> dict[str, str]:
        try:
            return self._launch_fire(command)
        except (ApplicationError, DomainValidationError, ValidationError) as exc:
            code = exc.code if isinstance(exc, ApplicationError) else "schedule_definition_invalid"
            try:
                self.schedules.fires.launch_failed(command["triggerId"], code)
            except Exception:
                raise TemporalApplicationError(
                    "Fire evidence storage is unavailable", type="schedule_evidence_unavailable"
                ) from None
            raise TemporalApplicationError(
                "Scheduled launch was rejected", type=code, non_retryable=True
            ) from None
        except Exception:
            raise TemporalApplicationError(
                "Schedule launch storage is unavailable", type="schedule_launch_unavailable"
            ) from None

    def _launch_fire(self, command: dict[str, Any]) -> dict[str, str]:
        launch_id = "schedule-fire:" + command["triggerId"]
        scheduled_at = datetime.fromisoformat(command["scheduledAt"])
        requested_at = self.schedules.requested_time(command["scheduleId"], scheduled_at)
        self.schedules.fires.record(
            ScheduleFireRecord(
                trigger_id=command["triggerId"],
                schedule_id=command["scheduleId"],
                scheduled_at=requested_at or scheduled_at,
                engine_workflow_id=command["engineWorkflowId"],
                engine_run_id=command["engineRunId"],
                status="pending",
                updated_at=datetime.now(UTC),
            )
        )
        existing = self.store.get_run_by_launch_id(launch_id)
        if existing is None:
            definition = command["definition"]
            summary = self.launch_service.launch(
                definition["packageKey"],
                definition["workflowKey"],
                definition["parameters"],
                launch_id=launch_id,
                origin=LaunchOrigin(
                    kind="schedule",
                    schedule_id=command["scheduleId"],
                    trigger_id=command["triggerId"],
                    scheduled_at=requested_at or scheduled_at,
                ),
            )
            existing = self.store.get_run(summary.id)
        if existing is None:
            raise ApplicationError("run_not_found", "Run snapshot is unavailable", status=404)
        self.schedules.fires.launched(command["triggerId"], existing.id)
        return {"runId": existing.id, "deadline": existing.spec.deadline.isoformat()}

    @activity.defn(name="wait_scheduled_run")
    async def wait_run(self, run_id: str) -> None:
        try:
            await self._wait_run(run_id)
        except (asyncio.CancelledError, TemporalApplicationError):
            raise
        except Exception:
            raise TemporalApplicationError(
                "Scheduled Run is temporarily unavailable", type="scheduled_run_unavailable"
            ) from None

    async def _wait_run(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        if run is None:
            raise TemporalApplicationError(
                "Run snapshot is unavailable", type="run_not_found", non_retryable=True
            )
        try:
            await CommandDispatcher(self.store, self.engine).dispatch_start(run_id)
        except AdmissionRejected as exc:
            self.schedules.fires.finished(run_id, "failed", exc.code)
            raise TemporalApplicationError(
                "Scheduled Run was not admitted", type=exc.code, non_retryable=True
            ) from None

        async def heartbeat() -> None:
            while True:
                activity.heartbeat(run_id)
                await asyncio.sleep(3)

        heartbeat_task = asyncio.create_task(heartbeat())
        try:
            result = await self.engine.result(run_id)
            self._finished(run_id, result)
        except asyncio.CancelledError:
            if not activity.is_worker_shutdown():
                await self.engine.cancel(run_id)
                try:
                    result = await self.engine.result(run_id)
                    self._finished(run_id, result)
                except WorkflowFailureError:
                    await self._failed(run_id)
            raise
        except WorkflowFailureError:
            await self._failed(run_id)
            raise TemporalApplicationError(
                "Scheduled Run did not succeed", type="scheduled_run_failed", non_retryable=True
            ) from None
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

    def _finished(self, run_id: str, result: Any) -> None:
        if not isinstance(result, dict) or result.get("status") not in {
            "succeeded",
            "failed",
            "cancelled",
        }:
            raise TemporalApplicationError(
                "Invalid scheduled Run result", type="engine_result_invalid", non_retryable=True
            )
        self.schedules.fires.finished(run_id, result["status"], result.get("errorCode"))

    async def _failed(self, run_id: str) -> None:
        fact = await TemporalExecutionObserver(self.engine.client).terminal_fact(run_id)
        if fact is None:
            raise TemporalApplicationError(
                "Engine terminal fact is unavailable", type="engine_observation_unavailable"
            )
        self.schedules.fires.finished(run_id, fact.status, fact.error_code)

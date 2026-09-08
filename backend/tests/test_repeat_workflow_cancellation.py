"""Repeated caller cancellation sends one Temporal activity cancellation command."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path

from temporalio import activity, workflow
from temporalio.api.enums.v1 import EventType
from temporalio.exceptions import is_cancelled_exception
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.infrastructure.temporal_agent import io


@workflow.defn(sandboxed=False)
class RepeatCancellationWorkflow:
    def __init__(self):
        self.primary = None
        self.repeated = False

    @workflow.run
    async def run(self) -> str:
        self.primary = asyncio.current_task()
        try:
            await io("deterministic_agent", {}, timeout=30)
        except asyncio.CancelledError:
            return "cancelled"
        except Exception as exc:
            if is_cancelled_exception(exc):
                return "cancelled"
            raise
        return "completed"

    @workflow.signal
    def cancel_again(self) -> None:
        assert self.primary is not None
        self.repeated = True
        self.primary.cancel()

    @workflow.query
    def received_repeat(self) -> bool:
        return self.repeated


def test_repeated_workflow_cancellation_waits_for_one_activity_stop(tmp_path):
    async def scenario():
        entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        diagnostics = Path(os.environ.get("SIGNALDECK_CANCEL_DIAGNOSTICS", str(tmp_path)))
        diagnostics.mkdir(parents=True, exist_ok=True)

        @activity.defn(name="deterministic_agent")
        async def held_activity(payload: dict) -> None:
            entered.set()
            try:
                while True:
                    activity.heartbeat()
                    await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                cleaning.set()
                await release.wait()
                raise

        async with await WorkflowEnvironment.start_local(
            dev_server_existing_path=os.environ.get("TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal")
        ) as environment:
            async with Worker(
                environment.client,
                task_queue="repeat-cancel",
                workflows=[RepeatCancellationWorkflow],
                activities=[held_activity],
                default_heartbeat_throttle_interval=timedelta(milliseconds=50),
                max_heartbeat_throttle_interval=timedelta(milliseconds=100),
            ):
                handle = await environment.client.start_workflow(
                    RepeatCancellationWorkflow.run,
                    id="repeat-workflow-cancellation",
                    task_queue="repeat-cancel",
                )
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    await handle.cancel()
                    await asyncio.wait_for(cleaning.wait(), 5)
                    await handle.signal(RepeatCancellationWorkflow.cancel_again)
                    assert await handle.query(
                        RepeatCancellationWorkflow.received_repeat,
                        rpc_timeout=timedelta(seconds=3),
                    )
                    release.set()
                    assert await asyncio.wait_for(handle.result(), 5) == "cancelled"
                    history = await handle.fetch_history(rpc_timeout=timedelta(seconds=3))
                    event_types = [event.event_type for event in history.events]
                    assert (
                        event_types.count(EventType.EVENT_TYPE_ACTIVITY_TASK_CANCEL_REQUESTED) == 1
                    )
                    assert EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED not in event_types
                    assert EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED in event_types
                finally:
                    release.set()
                    try:
                        history = await handle.fetch_history(rpc_timeout=timedelta(seconds=3))
                        (diagnostics / "history.json").write_text(history.to_json())
                        summary = {
                            "events": [
                                EventType.Name(event.event_type) for event in history.events
                            ],
                            "failures": [
                                event.workflow_task_failed_event_attributes.failure.message
                                for event in history.events
                                if event.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED
                            ],
                        }
                        (diagnostics / "summary.json").write_text(json.dumps(summary, indent=2))
                    except Exception as exc:
                        (diagnostics / "diagnostic-error.txt").write_text(type(exc).__name__)

    asyncio.run(scenario())

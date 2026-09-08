"""Verify explicit Prefect Automation resubmits one killed Run to a live Runner."""

import asyncio
import json
import os
import signal
import time
from datetime import UTC, datetime, timedelta

from prefect.automations import Automation
from prefect.client.orchestration import get_client
from prefect.events.actions import ChangeFlowRunState
from prefect.events.schemas.automations import EventTrigger
from prefect.runner import Runner
from prefect.states import Scheduled, StateType
from probe import events, spec, wait_for
from workloads import ROOT, agent_flow


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    runner = Runner(name="sd-prefect-auto", query_seconds=0.2, pause_on_shutdown=False)
    deployment = await agent_flow.to_deployment(name="automatic-recovery")
    deployment_id = await runner.aadd_deployment(deployment)
    automation = None
    run_task = asyncio.create_task(runner.start())
    try:
        async with get_client() as client:
            run = await client.create_flow_run_from_deployment(
                deployment_id,
                parameters={"spec": spec("auto-recovery", crash=True)},
                state=Scheduled(scheduled_time=datetime.now(UTC) + timedelta(seconds=3)),
            )
            automation = await Automation(
                name=f"sd-prefect-single-crash-{run.id}",
                trigger=EventTrigger(
                    expect={"prefect.flow-run.Crashed"},
                    match={"prefect.resource.id": f"prefect.flow-run.{run.id}"},
                ),
                actions=[ChangeFlowRunState(state=StateType.SCHEDULED, force=True)],
            ).acreate()
            await wait_for(lambda: (ROOT / "confirmed").exists())
            await wait_for(lambda: any(x["kind"] == "node_end" for x in events()))
            pid = next(x["pid"] for x in events() if x["kind"] == "model")
            os.kill(pid, signal.SIGKILL)
            (ROOT / "release").write_text("continue after native automation")
            end = time.monotonic() + 45
            while True:
                actual = await client.read_flow_run(run.id)
                if actual.state.is_completed():
                    break
                if time.monotonic() >= end:
                    raise TimeoutError(f"automation did not complete: {actual.state}")
                await asyncio.sleep(0.1)
            calls = events()
            assert len([x for x in calls if x["kind"] == "tool"]) == 2
            assert len([x for x in calls if x["kind"] == "model" and x["round"] == 0]) == 1
            assert len([x for x in calls if x["kind"] == "node_end"]) == 1
            assert actual.run_count == 2
            result = {
                "passed": True,
                "flowRunId": str(run.id),
                "runCount": actual.run_count,
                "state": actual.state.name,
                "events": calls,
                "note": "engine Automation + live Runner; same identity and confirmed call cache",
                "limits": "single fixture automation; bounded production crash policy not proven",
            }
            (ROOT / "report.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
    finally:
        if automation is not None:
            await automation.adelete()
        await runner.astop()
        await run_task


if __name__ == "__main__":
    asyncio.run(main())

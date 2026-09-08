"""Observe native Runner handling of a killed flow subprocess with retries=1."""

import asyncio
import json
import os
import signal
import time

from prefect.client.orchestration import get_client
from prefect.runner import Runner
from probe import events, spec, wait_for
from workloads import ROOT, agent_flow


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    runner = Runner(name="sd-prefect-crash", query_seconds=0.2, pause_on_shutdown=False)
    deployment = await agent_flow.with_options(retries=1).to_deployment(name="crash-retries")
    # Register the file entrypoint, not a live Agent closure containing ContextVars.
    deployment_id = await runner.aadd_deployment(deployment)
    run_task = asyncio.create_task(runner.start())
    try:
        async with get_client() as client:
            run = await client.create_flow_run_from_deployment(
                deployment_id, parameters={"spec": spec("managed-crash", crash=True)}
            )
            await wait_for(lambda: (ROOT / "confirmed").exists())
            pid = next(x["pid"] for x in events() if x["kind"] == "model")
            os.kill(pid, signal.SIGKILL)
            end = time.monotonic() + 20
            while True:
                actual = await client.read_flow_run(run.id)
                if actual.state.is_final():
                    break
                if time.monotonic() >= end:
                    raise TimeoutError("native crash state not settled")
                await asyncio.sleep(0.1)
            result = {
                "flowRunId": str(run.id),
                "state": actual.state.name,
                "flowRetries": actual.empirical_policy.retries,
                "runCount": actual.run_count,
                "automaticRecoveryPassed": actual.state.is_completed(),
                "note": "Live Runner observed killed subprocess; no resubmit automation.",
            }
            (ROOT / "report.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
    finally:
        await runner.astop()
        await run_task


if __name__ == "__main__":
    asyncio.run(main())

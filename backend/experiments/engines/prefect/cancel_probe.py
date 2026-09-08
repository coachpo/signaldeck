"""Exercise API cancellation through Prefect's actual subprocess executor."""

import asyncio
import json
import subprocess
import sys
import time

from prefect.client.orchestration import get_client
from prefect.states import Cancelling
from workloads import ROOT, cancel_flow


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    deployment = await cancel_flow.to_deployment(name="api-cancel")
    deployment_id = await deployment.apply()
    async with get_client() as client:
        run = await client.create_flow_run_from_deployment(deployment_id)
        with (ROOT / "executor.log").open("w") as log:
            executor = subprocess.Popen(
                [sys.executable, "-m", "prefect", "flow-run", "execute", str(run.id)],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + 40
            while not (ROOT / "events.jsonl").exists():
                if executor.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("executor failed to start cancellation workload")
                await asyncio.sleep(0.1)
            await client.set_flow_run_state(run.id, Cancelling())
            await asyncio.to_thread(executor.wait, 45)
        state = await client.read_flow_run(run.id)
        observations = [
            json.loads(line) for line in (ROOT / "events.jsonl").read_text().splitlines()
        ]
        assert state.state.is_cancelled(), state.state
        assert not any(event["kind"] == "forbidden_downstream" for event in observations)
        assert any(event["kind"] == "cancel_propagated" for event in observations)
        result = {
            "passed": True,
            "flowRunId": str(run.id),
            "state": state.state.name,
            "executorExit": executor.returncode,
            "events": observations,
            "note": "API Cancelling -> subprocess Cancelled; finally observed, no downstream",
        }
        (ROOT / "report.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

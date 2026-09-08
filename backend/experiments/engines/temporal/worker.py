"""Worker subprocess used for actual hard-interruption tests."""

import asyncio
import os

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from runtime import AgentWorkflow, GraphWorkflow, RecoveryWorkflow, node
from temporalio.client import Client
from temporalio.worker import Worker


async def main():
    client = await Client.connect(os.environ["PROBE_ADDRESS"], plugins=[PydanticAIPlugin()])
    async with Worker(
        client,
        task_queue="sd-target-temporal-probe",
        workflows=[AgentWorkflow, GraphWorkflow, RecoveryWorkflow],
        activities=[node],
    ):
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

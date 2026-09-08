"""Live operation ownership survives duplicate delivery through the real worker adapter."""

import asyncio
import os
from datetime import UTC, datetime, timedelta

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.testing import WorkflowEnvironment

from app.application.tool_gateway import ToolGateway
from app.domain.tool_contracts import ToolResult, tool_contract_digest
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.evidence_store import PostgresToolEvidenceStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import TemporalServices
from app.workers import durable_worker
from tests.test_durable_runtime_support import CORE, make_release, make_spec
from tests.test_platform_persistence import prepare_tree
from tests.test_tool_gateway_target import Transport


@workflow.defn(sandboxed=False)
class DuplicateDeterministicDelivery:
    @workflow.run
    async def run(self, payload: dict) -> list:
        # The harness delivers the same logical invocation through two real Activities.
        return await asyncio.gather(
            *(
                workflow.execute_activity(
                    "deterministic_agent",
                    payload,
                    start_to_close_timeout=timedelta(seconds=30),
                    heartbeat_timeout=timedelta(seconds=3),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                for _ in range(2)
            )
        )


def test_live_write_redelivery_waits_without_failing_agent(session_factory, tmp_path, monkeypatch):
    async def scenario():
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(session_factory, artifacts=artifacts)
        store.initialize()
        prepare_tree(store)
        entered, busy, release_write = asyncio.Event(), asyncio.Event(), asyncio.Event()

        class ObservedGateway(ToolGateway):
            async def call(self, *args, **kwargs):
                result = await super().call(*args, **kwargs)
                if result.code == "operation_in_progress":
                    busy.set()
                return result

        class HeldWrite(Transport):
            def __init__(self):
                super().__init__([])
                self.effects = 0

            async def execute(self, release, tool, arguments, context):
                self.calls += 1
                entered.set()
                await release_write.wait()
                self.effects += 1
                return ToolResult(status="succeeded", output=arguments)

        monkeypatch.setattr(durable_worker, "ToolGateway", ObservedGateway)
        transport = HeldWrite()
        release = make_release()
        writer = release.tools[0].model_copy(update={"effect": "write"})
        release = release.model_copy(
            update={"tools": (writer,), "contract_digest": tool_contract_digest((writer,))}
        )
        payload = {
            "runId": "run-1",
            "nodeId": "n",
            "invocationId": "agent",
            "agent": make_spec().definition["agents"]["shared"],
            "input": {"value": 1, "tag": "redelivery", "delay": 0},
            "deadline": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
            "resourceBindings": {},
            "pluginReleases": [release.model_dump(mode="json", by_alias=True)],
        }
        async with await WorkflowEnvironment.start_local(
            dev_server_existing_path=os.environ.get(
                "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
            ),
            data_converter=create_data_converter(artifacts),
            plugins=[PydanticAIPlugin()],
        ) as environment:
            services = TemporalServices(
                store, artifacts, lambda bindings: transport, CORE, lambda: None
            )
            async with await durable_worker.create_worker(
                environment.client,
                services,
                "operation-redelivery",
                workflows=[DuplicateDeterministicDelivery],
            ):
                handle = await environment.client.start_workflow(
                    DuplicateDeterministicDelivery.run,
                    payload,
                    id="overlapping-deterministic-delivery",
                    task_queue="operation-redelivery",
                )
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    await asyncio.wait_for(busy.wait(), 5)
                    assert transport.calls == 1 and transport.effects == 0
                    release_write.set()
                    result = await asyncio.wait_for(handle.result(), 8)
                    assert result == [payload["input"], payload["input"]]
                    assert transport.calls == transport.effects == 1
                    evidence = PostgresToolEvidenceStore(session_factory, artifacts)
                    operation = await evidence.get_operation("agent:tool:deterministic")
                    assert operation is not None and operation.status == "succeeded"
                    assert await evidence.count_execute_attempts("agent:tool:deterministic") == 1
                finally:
                    release_write.set()

    asyncio.run(scenario())

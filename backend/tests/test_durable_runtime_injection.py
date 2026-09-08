"""A process can host two workers without sharing their I/O capabilities."""

import asyncio
import json
import os

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import TemporalServices
from app.workers.durable_worker import create_worker
from tests.test_durable_runtime_support import CORE, make_spec, mapping, model_server, tool_server


def test_two_workers_in_one_process_keep_distinct_store_gateway_and_credentials(
    database_url, tmp_path
):
    async def scenario():
        first_engine = create_engine(database_url)
        with first_engine.begin() as connection:
            connection.execute(text("CREATE SCHEMA worker_two"))
        second_engine = create_engine(
            database_url, execution_options={"schema_translate_map": {None: "worker_two"}}
        )
        artifacts = ArtifactStore(tmp_path / "artifacts")
        first_store = PlatformStore(
            sessionmaker(first_engine, expire_on_commit=False), artifacts=artifacts
        )
        second_store = PlatformStore(
            sessionmaker(second_engine, expire_on_commit=False), artifacts=artifacts
        )
        for store, credential in [
            (first_store, "first-worker-key"),
            (second_store, "second-worker-key"),
        ]:
            store.initialize()
            store.save_resource("model", "model", {}, {"apiKey": credential})
        first_events, second_events, calls, credentials = [], [], [], []
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=os.environ.get(
                    "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                ),
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            tool_server(first_events, offset=1) as first_transport,
            tool_server(second_events, offset=100) as second_transport,
            model_server(calls, credential_log=credentials) as url,
        ):
            first = await create_worker(
                environment.client,
                TemporalServices(
                    first_store,
                    artifacts,
                    lambda bindings: first_transport,
                    CORE,
                    lambda: None,
                ),
                "worker-one",
            )
            second = await create_worker(
                environment.client,
                TemporalServices(
                    second_store,
                    artifacts,
                    lambda bindings: second_transport,
                    CORE,
                    lambda: None,
                ),
                "worker-two",
            )
            specs = [
                make_spec(
                    {"a": {"uses": "shared", "inputMapping": mapping(tag, {"value": 7})}},
                    kind="model",
                    model_url=url,
                    model_store=bound_store,
                )
                for tag, bound_store in zip(
                    ["one", "two"], [first_store, second_store], strict=True
                )
            ]
            first_store.create_run(specs[0], specs[0].run_id)
            second_store.create_run(specs[1], specs[1].run_id)
            async with first, second:
                results = await asyncio.wait_for(
                    asyncio.gather(
                        *(
                            environment.client.execute_workflow(
                                "SignalDeckWorkflow",
                                spec.model_dump(mode="json", by_alias=True),
                                id=spec.run_id,
                                task_queue=queue,
                            )
                            for spec, queue in zip(specs, ["worker-one", "worker-two"], strict=True)
                        )
                    ),
                    25,
                )
            assert [value["status"] for value in results] == ["succeeded", "succeeded"]
            assert [value["output"]["value"] for value in results] == [8, 107]
            assert {tag for _, tag, _ in first_events} == {"one"}
            assert {tag for _, tag, _ in second_events} == {"two"}
            assert set(credentials) == {"Bearer first-worker-key", "Bearer second-worker-key"}
            for credential, call in zip(credentials, calls, strict=True):
                prompt = json.loads(
                    next(
                        message["content"]
                        for message in call["messages"]
                        if message["role"] == "user"
                    )
                )
                expected = (
                    "Bearer first-worker-key"
                    if prompt["input"]["tag"] == "one"
                    else "Bearer second-worker-key"
                )
                assert credential == expected

            assert first_store.get_run(specs[1].run_id) is None
            assert second_store.get_run(specs[0].run_id) is None
            for store, spec in [(first_store, specs[0]), (second_store, specs[1])]:
                detail = store.get_run(spec.run_id)
                assert detail.status == "succeeded"
                assert all(
                    e.run_id == spec.run_id and e.status == "succeeded" for e in detail.evidence
                )
        first_engine.dispose()
        second_engine.dispose()

    asyncio.run(scenario())

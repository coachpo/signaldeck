"""Explicit cross-Run reads preserve source evidence and enforce caller freshness."""

import asyncio
import os
from datetime import UTC, datetime, timedelta

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import TemporalServices
from app.workers.durable_worker import create_worker
from tests.test_durable_runtime_support import (
    CORE,
    make_spec,
    model_server,
    recompile_spec,
    tool_server,
)


def test_explicit_cache_across_runs_and_model_strategy_has_source_and_ttl(database_url, tmp_path):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "cache-model-key"})
        calls, events = [], []
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=os.environ.get(
                    "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                ),
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            tool_server(events) as transport,
            model_server(calls) as url,
        ):
            services = TemporalServices(
                store, artifacts, lambda bindings: transport, CORE, lambda: None
            )
            async with await create_worker(environment.client, services, "cache-runtime-test"):

                async def execute(ttl=None, kind="deterministic"):
                    spec = make_spec(kind=kind, model_url=url, model_store=store)
                    if ttl is not None:
                        spec.definition["agents"]["shared"]["toolCache"] = {
                            "example/probe/search": {"ttlSeconds": ttl}
                        }
                    spec = recompile_spec(spec)
                    store.create_run(spec, spec.run_id)
                    result = await environment.client.execute_workflow(
                        "SignalDeckWorkflow",
                        spec.model_dump(mode="json", by_alias=True),
                        id=spec.run_id,
                        task_queue="cache-runtime-test",
                    )
                    detail = store.get_run(spec.run_id)
                    assert result["status"] == "succeeded", detail
                    evidence = next(e for e in detail.evidence if e.kind == "tool")
                    return spec, evidence

                await execute()
                await execute()
                assert len([e for e in events if e[0] == "start"]) == 2
                source, first = await execute(60)
                assert first.metadata["cacheProvenance"]["hit"] is False
                cached, hit = await execute(60)
                assert cached.run_id != source.run_id
                provenance = hit.metadata["cacheProvenance"]
                assert provenance["hit"] is True
                assert provenance["sourceRunId"] == source.run_id
                assert provenance["sourceOperationId"] == first.operation_id
                assert provenance["fetchedAt"] == first.metadata["cacheProvenance"]["fetchedAt"]
                assert len([e for e in events if e[0] == "start"]) == 3
                _, model_hit = await execute(60, "model")
                assert model_hit.metadata["cacheProvenance"]["sourceRunId"] == source.run_id
                assert model_hit.metadata["cacheProvenance"]["hit"] is True
                assert (
                    len(calls) == 2
                )  # Model data is fresh; only explicitly selected tool is cached.
                assert len([e for e in events if e[0] == "start"]) == 3
                # A stricter new caller TTL cannot inherit the cached source's longer validity.
                stale_at = datetime.fromisoformat(provenance["fetchedAt"]) + timedelta(seconds=1.1)
                await asyncio.sleep(max(0, (stale_at - datetime.now(UTC)).total_seconds()))
                refreshed, fresh = await execute(1)
                assert fresh.metadata["cacheProvenance"]["hit"] is False
                assert fresh.metadata["cacheProvenance"]["sourceRunId"] == refreshed.run_id
                assert len([e for e in events if e[0] == "start"]) == 4
                _, no_policy = await execute()
                assert no_policy.metadata["cacheProvenance"] is None
                assert len([e for e in events if e[0] == "start"]) == 5
        engine.dispose()

    asyncio.run(scenario())

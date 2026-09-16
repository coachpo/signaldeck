"""Actual research package on Temporal, scheduled fires, MCP and isolated PostgreSQL."""

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.application.launch import LaunchService
from app.domain.compiler import compile_package
from app.domain.definition_parser import parse_package_source
from app.domain.schedules import ScheduleDefinition
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.core_artifacts import task_queue
from app.infrastructure.mcp_transport import McpToolTransport
from app.infrastructure.platform_models import RunRow
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.schedule_store import ScheduleStore
from app.infrastructure.temporal_dispatch import TemporalRunEngine
from app.infrastructure.temporal_schedules import TemporalScheduleService
from app.infrastructure.temporal_services import FrozenSecretResolver, TemporalServices
from app.workers.durable_worker import create_worker
from app.workers.schedule_fire import ScheduleFireWorkflow, TemporalScheduleActivities
from tests.conftest import database_url as isolated_database
from tests.test_research_runtime_support import (
    ROOT,
    Report,
    ResearchSnapshot,
    models,
    plugins,
    until,
)
from tests.test_target_schedules import CORE, StaticCore, server


@pytest.fixture
def finance_database_url():
    yield from isolated_database.__wrapped__()


def test_research_save_and_scheduled_monitor_transitions(
    database_url, finance_database_url, tmp_path, monkeypatch
):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        schedules = ScheduleStore(store.session_factory)
        schedules.initialize()
        source = dict(value="100", complete=True)
        calls = []
        parsed = parse_package_source((ROOT / "demo/us_equity_research.yaml").read_text())
        compiled = compile_package(parsed.package)
        key = compiled.package.metadata.key
        store.save_package(
            key,
            "runtime",
            compiled.package.model_dump(mode="json", by_alias=True),
            {},
            compiled.content_hash,
        )
        try:
            async with (
                plugins(finance_database_url, monkeypatch, source) as (finance, url, releases),
                models(calls) as model_url,
            ):
                for release in releases:
                    store.install_plugin(release["pluginId"], release)
                store.save_resource(
                    "equity-research-model",
                    "model",
                    dict(baseUrl=model_url, modelId="research", apiStyle="chat_completions"),
                    dict(apiKey="controlled"),
                )
                store.save_resource(
                    "finance-market-data",
                    "tool",
                    dict(pluginId="signaldeck/finance", scope=dict(allowedSymbols=["NVDA"])),
                    {},
                )
                async with await server(artifacts) as environment:
                    services = TemporalServices(
                        store,
                        artifacts,
                        lambda spec: McpToolTransport(
                            FrozenSecretResolver(store.resolve_bound_credentials, spec)
                        ),
                        CORE,
                        lambda: None,
                    )
                    launcher = LaunchService(store, StaticCore())
                    schedule_activities = TemporalScheduleActivities(
                        launcher,
                        store,
                        TemporalRunEngine(environment.client, StaticCore()),
                        schedules,
                    )
                    worker = await create_worker(
                        environment.client,
                        services,
                        task_queue(CORE),
                        workflows=[ScheduleFireWorkflow],
                        activities=[schedule_activities.launch_fire, schedule_activities.wait_run],
                    )
                    async with worker:

                        async def run(workflow, parameters):
                            summary = launcher.launch(key, workflow, parameters)
                            spec = store.get_run(summary.id).spec
                            result = await asyncio.wait_for(
                                environment.client.execute_workflow(
                                    "SignalDeckWorkflow",
                                    spec.model_dump(mode="json", by_alias=True),
                                    id=summary.id,
                                    task_queue=task_queue(CORE),
                                ),
                                90,
                            )
                            detail = store.get_run(summary.id)
                            assert result["status"] == "succeeded", [
                                (e.node_id, e.kind, e.status, e.error_code)
                                for e in detail.evidence
                                if e.status not in {"succeeded", "skipped"}
                            ]
                            return detail

                        research = await run(
                            "research",
                            dict(
                                symbol="NVDA",
                                asOfDate=datetime.now(UTC).date().isoformat(),
                                question="Cash generation",
                                horizonMonths=3,
                            ),
                        )
                        assert len(calls) == 10
                        await verify_saved(finance, url, research)
                        parameters = dict(
                            monitorKey="scheduled-research",
                            scope=dict(
                                symbol="NVDA",
                                cik="0001045810",
                                question="Cash generation",
                                horizonMonths=3,
                                ruleVersion="1",
                                sources=[
                                    dict(sourceId="sec", required=True, maxAgeSeconds=3600),
                                ],
                                rules=[],
                            ),
                        )
                        service = TemporalScheduleService(
                            environment.client, schedules, task_queue(CORE)
                        )
                        schedule = ScheduleDefinition(
                            name="Research",
                            package_key=key,
                            workflow_key="monitor",
                            parameters=parameters,
                            cron="* * * * *",
                            paused=False,
                        ).model_copy(update={"cron": "*/5 * * * * * *"})
                        record = await service.save(schedule)
                        try:

                            def completed():
                                # Keep polling cheap: full Run reads include the frozen package
                                # and every node/model payload and would stall this event loop.
                                with store.session_factory() as session:
                                    runs = session.execute(
                                        select(RunRow.id, RunRow.status).where(
                                            RunRow.spec["workflowKey"].astext == "monitor"
                                        )
                                    ).all()
                                for run_id, status in runs:
                                    if status in {"failed", "timed_out"}:
                                        detail = store.get_run(run_id)
                                        pytest.fail(
                                            str(
                                                [
                                                    (e.node_id, e.kind, e.status, e.error_code)
                                                    for e in detail.evidence
                                                    if e.status not in {"succeeded", "skipped"}
                                                ]
                                            )
                                        )
                                return [run_id for run_id, status in runs if status == "succeeded"]

                            await until(lambda: len(completed()) >= 2, timeout=180)
                        finally:
                            await service.delete(record.id)
                        observations = sorted(
                            [store.get_run(run_id) for run_id in completed()],
                            key=lambda item: item.origin.scheduled_at,
                        )
                        first, second = observations[:2]
                        assert first.output["state"] == "no_baseline", first.output
                        assert second.output["state"] == "unchanged", second.output
                        assert first.origin.schedule_id == second.origin.schedule_id == record.id
                        assert first.origin.scheduled_at < second.origin.scheduled_at
                        assert (
                            first.spec.package_hash
                            == second.spec.package_hash
                            == compiled.content_hash
                        )
                        assert (
                            first.spec.definition
                            == second.spec.definition
                            == research.spec.definition
                        )
                        assert len(calls) == 20
                        await verify_saved(finance, url, first)
                        assert not [e for e in second.evidence if e.kind == "model"]
                        with finance.state.sessions() as session:
                            previous = session.get(ResearchSnapshot, first.output["snapshotId"])
                            current = session.get(ResearchSnapshot, second.output["snapshotId"])
                            assert current.cutoff_at > previous.cutoff_at
                            assert current.previous_snapshot_id == previous.id
                        source["complete"] = False
                        invalid = await run("monitor", parameters)
                        assert invalid.output["state"] == "invalid"
                        assert not [e for e in invalid.evidence if e.kind == "model"]
                        source.update(complete=True, value="120")
                        changed = await run("monitor", parameters)
                        assert changed.output["state"] == "changed", changed.output
                        assert len(calls) == 30
                        await verify_saved(finance, url, changed)
                        with finance.state.sessions() as session:
                            current = session.get(ResearchSnapshot, changed.output["snapshotId"])
                            assert current.previous_snapshot_id == second.output["snapshotId"]
                            assert len(session.scalars(select(Report)).all()) == 3
        finally:
            engine.dispose()

    asyncio.run(scenario())


async def verify_saved(finance, url, detail):
    compiled = next(
        e.output for e in detail.evidence if e.kind == "node" and e.node_id == "compile"
    )
    with finance.state.sessions() as session:
        report = session.get(Report, detail.output["reportId"])
        assert report.content == compiled["content"] == detail.output["content"]
        slug = report.slug
        assert report.metadata_["createdBy"]["runId"] == detail.id
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{url}/api/reports/{slug}/download")
        assert response.status_code == 200
        assert response.text == detail.output["content"]

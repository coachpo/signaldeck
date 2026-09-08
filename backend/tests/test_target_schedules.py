"""Real Temporal/PostgreSQL delivery and Schedule lifecycle regression scenarios."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from temporalio import workflow
from temporalio.client import ScheduleBackfill, ScheduleOverlapPolicy, WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from app.application.dispatch import AdmissionRejected, CommandDispatcher
from app.application.launch import LaunchService
from app.domain.compiler import compile_package
from app.domain.execution import ApplicationError
from app.domain.schedules import ScheduleDefinition, ScheduleFireRecord
from app.domain.tool_contracts import PluginRelease, ToolDefinition, tool_contract_digest
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.core_artifacts import CoreArtifactError, CoreArtifactStore, task_queue
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.schedule_store import ScheduleStore, ScheduleTriggerRow
from app.infrastructure.temporal_dispatch import TemporalRunEngine
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_schedules import TemporalScheduleService, engine_schedule_id
from app.workers.schedule_fire import ScheduleFireWorkflow, TemporalScheduleActivities

CORE = "sha256:" + "c" * 64


class StaticCore:
    def current_digest(self):
        return CORE

    def verify(self, digest):
        # Lifecycle fixtures deliberately substitute only the executable loader.
        assert digest == CORE


@workflow.defn(name="SignalDeckWorkflow")
class ControlledRun:
    """A real engine execution held open independently of the query projection."""

    def __init__(self):
        self.released = False

    @workflow.run
    async def run(self, spec: dict) -> dict:
        if spec["workflowKey"] != "fast":
            await workflow.wait_condition(lambda: self.released)
        return {"status": "succeeded"}

    @workflow.signal
    def release(self):
        self.released = True


@pytest.fixture()
def stores(database_url, tmp_path):
    database = create_engine(database_url)
    sessions = sessionmaker(database, expire_on_commit=False)
    artifacts = ArtifactStore(tmp_path / "artifacts")
    store = PlatformStore(sessions, artifacts=artifacts)
    schedules = ScheduleStore(sessions)
    store.initialize()
    schedules.initialize()
    tool = ToolDefinition(
        tool_id="example/schedule/echo",
        owner_plugin_id="example/schedule",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    release = PluginRelease(
        plugin_id="example/schedule",
        release_id="one",
        artifact_digest="sha256:" + "d" * 64,
        endpoint="http://unused.invalid/mcp",
        tools=(tool,),
        contract_digest=tool_contract_digest((tool,)),
    )
    store.install_plugin(release.plugin_id, release.model_dump(mode="json", by_alias=True))
    definition = {
        "metadata": {"key": "scheduled", "name": "Scheduled"},
        "agents": {
            "worker": {
                "inputSchema": {"type": "object"},
                "outputSchema": {"type": "object"},
                "strategy": {"kind": "deterministic", "toolId": tool.tool_id},
                "tools": [tool.tool_id],
            }
        },
        "workflows": {
            name: {
                "inputSchema": {"type": "object"},
                "outputSchema": {"type": "object"},
                "nodes": {"run": {"uses": "worker", "inputMapping": {"ref": "workflow.input"}}},
                "outputMapping": {"ref": "nodes.run.output"},
                "deadlineSeconds": 120,
            }
            for name in ("slow", "fast")
        },
    }
    compiled = compile_package(definition)
    store.save_package(
        "scheduled",
        "fixture",
        compiled.package.model_dump(mode="json", by_alias=True),
        {},
        compiled.content_hash,
    )
    yield store, schedules, artifacts
    database.dispose()


def definition(**updates):
    return ScheduleDefinition(
        name="Schedule",
        package_key="scheduled",
        workflow_key="slow",
        cron="0 0 1 1 *",
        paused=False,
        **updates,
    )


async def until(predicate, timeout=15):
    async with asyncio.timeout(timeout):
        while not await predicate():
            await asyncio.sleep(0.05)


async def release(client, run_id):
    async def exists():
        try:
            await client.get_workflow_handle(run_id).signal("release")
            return True
        except RPCError as exc:
            if exc.status != RPCStatusCode.NOT_FOUND:
                raise
            return False

    await until(exists)


async def server(artifacts, **kwargs):
    cli = os.environ.get("TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal")
    assert Path(cli).is_file(), "TEMPORAL_CLI must point to pinned Temporal CLI 1.8.3"
    return await WorkflowEnvironment.start_local(
        dev_server_existing_path=cli,
        data_converter=create_data_converter(artifacts),
        plugins=[PydanticAIPlugin()],
        **kwargs,
    )


def worker(client, store):
    activities = TemporalScheduleActivities(
        LaunchService(store, StaticCore()),
        store,
        TemporalRunEngine(client, StaticCore()),
        ScheduleStore(store.session_factory),
    )
    # ControlledRun is a test-only engine lifecycle endpoint. Production runs use the
    # separately tested sandboxed DAG runtime; no application work is stubbed in the client.
    return Worker(
        client,
        task_queue=task_queue(CORE),
        workflows=[ControlledRun, ScheduleFireWorkflow],
        activities=[activities.launch_fire, activities.wait_run],
        workflow_runner=UnsandboxedWorkflowRunner(),
    )


@asynccontextmanager
async def stack(stores):
    store, schedule_store, artifacts = stores
    async with await server(artifacts) as environment:
        async with worker(environment.client, store):
            yield environment.client, TemporalScheduleService(
                environment.client, schedule_store, task_queue(CORE)
            )


def test_schedule_definition_contract():
    assert definition().catchup_window_seconds == 60
    for update in (
        {"time_zone": "invalid/zone"},
        {"catchup_window_seconds": 0},
        {"overlap_policy": "replace"},
    ):
        with pytest.raises(ValidationError):
            definition(**update)


def test_atomic_outbox_redelivery_uses_one_engine_execution(stores, monkeypatch):
    async def scenario():
        store, _, _ = stores
        async with stack(stores) as (client, _):
            run = LaunchService(store, StaticCore()).launch(
                "scheduled", "slow", {}, launch_id="launch-once"
            )
            assert store.get_run(run.id).spec.run_id == run.id
            assert len(store.pending_commands()) == 1
            engine = TemporalRunEngine(client, StaticCore())
            dispatcher = CommandDispatcher(store, engine)
            original = store.acknowledge_command
            monkeypatch.setattr(
                store,
                "acknowledge_command",
                lambda _: (_ for _ in ()).throw(RuntimeError("lost ack")),
            )
            assert await dispatcher.dispatch_once() == {"delivered": 0, "failed": 1}
            monkeypatch.setattr(store, "acknowledge_command", original)
            monkeypatch.setattr(
                engine.core_artifacts,
                "verify",
                lambda _: (_ for _ in ()).throw(CoreArtifactError("removed after accepted start")),
            )
            assert await dispatcher.dispatch_once() == {"delivered": 1, "failed": 0}
            assert len(store.list_runs()) == 1
            handle = client.get_workflow_handle(run.id)
            history = await handle.fetch_history()
            assert (
                sum(
                    item.HasField("workflow_execution_started_event_attributes")
                    for item in history.events
                )
                == 1
            )
            with pytest.raises(AdmissionRejected) as conflict:
                await engine.start(
                    store.get_run(run.id).spec.model_copy(update={"parameters": {"changed": True}})
                )
            assert conflict.value.code == "engine_identity_conflict"
            store.request_cancel(run.id)
            assert await dispatcher.dispatch_once() == {"delivered": 1, "failed": 0}

            async def cancelled():
                return (await handle.describe()).status == WorkflowExecutionStatus.CANCELED

            await until(cancelled)

    asyncio.run(scenario())


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_core_rejection_is_atomic_before_engine_start(stores, tmp_path, damage):
    async def scenario():
        store, _, artifacts = stores
        core = CoreArtifactStore(tmp_path / "core", source_root=Path(__file__).parents[1])
        run = LaunchService(store, core).launch("scheduled", "slow", {}, launch_id="not-admitted")
        digest = store.get_run(run.id).spec.core_artifact
        bundle = core.verify(digest)
        manifest = bundle.path / "manifest.json"
        original = manifest.read_bytes()
        moved = bundle.path.with_name(bundle.path.name + "-unavailable")
        if damage == "missing":
            bundle.path.rename(moved)
        else:
            manifest.chmod(0o644)
            manifest.write_bytes(b"corrupt")
        try:
            async with await server(artifacts) as environment:
                dispatcher = CommandDispatcher(store, TemporalRunEngine(environment.client, core))
                assert await dispatcher.dispatch_once() == {"delivered": 1, "failed": 0}
                detail = store.get_run(run.id)
                assert (
                    detail.status == "failed" and detail.error_code == "core_artifact_unavailable"
                )
                assert store.pending_commands() == []
                with pytest.raises(RPCError) as absent:
                    await environment.client.get_workflow_handle(run.id).describe()
                assert absent.value.status == RPCStatusCode.NOT_FOUND
                if damage == "missing":
                    moved.rename(bundle.path)
                else:
                    manifest.write_bytes(original)
                with pytest.raises(AdmissionRejected):
                    await dispatcher.dispatch_start(run.id)
                assert store.list_runs()[0].id == run.id
        finally:
            if moved.exists():
                moved.rename(bundle.path)
            if manifest.read_bytes() != original:
                manifest.write_bytes(original)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "policy,expected_before_release,expected_after_release",
    [
        ("skip", 1, 1),
        ("buffer_one", 1, 2),
        ("allow", 3, 3),
    ],
)
def test_overlap_tracks_actual_workflow(
    stores, policy, expected_before_release, expected_after_release
):
    async def scenario():
        store, _, _ = stores
        async with stack(stores) as (client, service):
            earliest = datetime.now(UTC) - timedelta(seconds=1)
            record = await service.save(definition(overlap_policy=policy))
            await service.trigger(record.id, "first")

            async def first_started():
                return len(store.list_runs()) == 1

            await until(first_started)
            first = store.list_runs()[0]
            # The query status is still queued: only actual engine completion releases overlap.
            assert first.status == "queued"
            await service.trigger(record.id, "second")
            await service.trigger(record.id, "third")
            handle = client.get_schedule_handle(engine_schedule_id(record.id))

            async def observed():
                description = await handle.describe()
                if policy == "skip":
                    return description.info.num_actions_skipped_overlap >= 2
                if policy == "buffer_one":
                    return description.raw_description.info.buffer_size == 1
                return len(store.list_runs()) == expected_before_release

            await until(observed)
            assert len(store.list_runs()) == expected_before_release
            if policy != "allow":
                assert (await handle.describe()).info.running_actions
            await release(client, first.id)

            async def subsequent():
                return len(store.list_runs()) == expected_after_release

            try:
                await until(subsequent)
            except TimeoutError:
                pytest.fail(
                    f"Unexpected buffered lifecycle: {[run.id for run in store.list_runs()]} "
                    f"{(await handle.describe()).raw_description.info}"
                )
            for run in store.list_runs():
                if run.id != first.id:
                    await release(client, run.id)
            await asyncio.gather(
                *(client.get_workflow_handle(run.id).result() for run in store.list_runs())
            )

            async def all_finished():
                return not (await handle.describe()).info.running_actions

            await until(all_finished)
            runs = store.list_runs()
            assert len(runs) == expected_after_release
            assert len({run.origin.trigger_id for run in runs}) == len(runs)
            assert all(
                run.origin.schedule_id == record.id and run.origin.scheduled_at for run in runs
            )
            assert all(earliest <= run.origin.scheduled_at <= datetime.now(UTC) for run in runs)
            assert len(stores[1].list_fires(record.id)) == len(runs)
            await service.delete(record.id)

    asyncio.run(scenario())


def test_configuration_failure_and_trigger_response_loss(stores):
    async def scenario():
        store, schedule_store, _ = stores
        async with stack(stores) as (client, service):
            invalid = definition().model_copy(update={"cron": "invalid cron"})
            with pytest.raises(ApplicationError) as rejected:
                await service.save(invalid, "bad")
            assert rejected.value.code == "schedule_invalid"
            assert schedule_store.get("bad").sync_status == "failed"
            record = await service.save(definition(), "bad")
            assert record.sync_status == "synced"

            def lost_ack(*_):
                raise RuntimeError("interrupt after engine accepted trigger")

            event.listen(ScheduleTriggerRow, "before_update", lost_ack)
            try:
                with pytest.raises(RuntimeError):
                    await service.trigger(record.id, "stable-trigger")
            finally:
                event.remove(ScheduleTriggerRow, "before_update", lost_ack)
            assert schedule_store.pending_triggers()[0].trigger_id == "stable-trigger"
            receipt = await service.trigger(record.id, "stable-trigger")
            assert receipt.status == "accepted"
            assert (await service.trigger(record.id, "stable-trigger")) == receipt

            async def fired():
                return len(store.list_runs()) == 1

            await until(fired)
            info = (await client.get_schedule_handle(engine_schedule_id(record.id)).describe()).info
            assert info.num_actions == 1
            assert info.num_actions_skipped_overlap == 0
            await release(client, store.list_runs()[0].id)

    asyncio.run(scenario())


def test_accepted_fire_retains_later_launch_failure(stores):
    async def scenario():
        store, schedules, _ = stores
        async with stack(stores) as (client, service):
            record = await service.save(definition())
            store.set_plugin_enabled("example/schedule", False)
            await service.trigger(record.id, "disabled-plugin")

            async def failed():
                fires = schedules.list_fires(record.id)
                return bool(fires) and fires[0].status == "launch_failed"

            await until(failed)
            fire = schedules.list_fires(record.id)[0]
            assert fire.error_code == "tool_unavailable" and fire.run_id is None
            assert fire.scheduled_at.year >= datetime.now(UTC).year
            assert store.list_runs() == []
            handle = client.get_schedule_handle(engine_schedule_id(record.id))

            async def closed():
                return not (await handle.describe()).info.running_actions

            await until(closed)
            store.set_plugin_enabled("example/schedule", True)
            broken = store.get_package("scheduled")["definition"]
            broken["workflows"]["slow"]["nodes"]["run"]["inputMapping"] = {
                "ref": "nodes.missing.output"
            }
            store.save_package(
                "scheduled", "invalid after schedule save", broken, {}, "invalid-revision"
            )
            await service.trigger(record.id, "invalid-definition")

            async def invalid_recorded():
                fires = schedules.list_fires(record.id)
                return len(fires) == 2 and all(f.status == "launch_failed" for f in fires)

            await until(invalid_recorded)
            fires = schedules.list_fires(record.id)
            assert {fire.error_code for fire in fires} == {
                "tool_unavailable",
                "schedule_definition_invalid",
            }
            assert store.list_runs() == []
            assert all(fire.engine_run_id and fire.engine_workflow_id for fire in fires)

    asyncio.run(scenario())


@pytest.mark.parametrize("policy", ["skip", "buffer_one"])
def test_calendar_tick_does_not_outlive_overlap_tracking(stores, policy):
    async def scenario():
        store, _, _ = stores
        async with stack(stores) as (client, service):
            record = await service.save(
                definition(overlap_policy=policy).model_copy(update={"cron": "* * * * * * *"})
            )
            handle = client.get_schedule_handle(engine_schedule_id(record.id))

            async def later_tick():
                info = (await handle.describe()).raw_description.info
                return info.overlap_skipped > 0 if policy == "skip" else info.buffer_size > 0

            await until(later_tick)
            assert len(store.list_runs()) == 1
            first = store.list_runs()[0]
            if policy == "skip":
                await service.delete(record.id)
            await release(client, first.id)
            if policy == "buffer_one":

                async def buffered_started():
                    return len(store.list_runs()) == 2

                await until(buffered_started)
                await service.delete(record.id)
                for run in store.list_runs():
                    if run.id != first.id:
                        await release(client, run.id)
            await asyncio.gather(
                *(client.get_workflow_handle(run.id).result() for run in store.list_runs())
            )
            assert all(run.origin.scheduled_at.year >= 1970 for run in store.list_runs())

    asyncio.run(scenario())


def test_manual_identity_range_cannot_be_selected_by_backfill(stores):
    async def scenario():
        store, _, _ = stores
        async with stack(stores) as (client, service):
            record = await service.save(
                definition(overlap_policy="allow").model_copy(
                    update={"cron": "* * * * * * *", "paused": True}
                )
            )
            await service.trigger(record.id, "manual-identity")

            async def accepted():
                return len(store.list_runs()) == 1

            await until(accepted)
            handle = client.get_schedule_handle(engine_schedule_id(record.id))
            await handle.backfill(
                ScheduleBackfill(
                    start_at=datetime(1899, 12, 31, 23, 59, 55, tzinfo=UTC),
                    end_at=datetime(1900, 1, 1, tzinfo=UTC),
                    overlap=ScheduleOverlapPolicy.ALLOW_ALL,
                )
            )
            assert (await handle.describe()).info.num_actions == 1
            assert store.list_runs()[0].origin.scheduled_at.year == datetime.now(UTC).year
            await release(client, store.list_runs()[0].id)

    asyncio.run(scenario())


def test_unfinished_fire_consumes_engine_timeout_without_creating_run(stores):
    async def scenario():
        store, schedules, artifacts = stores
        async with await server(artifacts) as environment:
            service = TemporalScheduleService(environment.client, schedules, task_queue(CORE))
            record = await service.save(definition())
            handle = await environment.client.start_workflow(
                "ScheduleFireWorkflow",
                {},
                id="accepted-fire-before-launch",
                task_queue="deliberately-unavailable-worker",
                execution_timeout=timedelta(milliseconds=150),
            )
            assert handle.first_execution_run_id is not None
            now = datetime.now(UTC)
            schedules.fires.record(
                ScheduleFireRecord(
                    trigger_id="pending-fire",
                    schedule_id=record.id,
                    scheduled_at=now,
                    engine_workflow_id=handle.id,
                    engine_run_id=handle.first_execution_run_id,
                    status="pending",
                    updated_at=now,
                )
            )

            async def timed_out():
                return (await handle.describe()).status == WorkflowExecutionStatus.TIMED_OUT

            await until(timed_out)
            assert await service.project_fires() == {
                "examined": 1,
                "projected": 1,
                "unavailable": 0,
            }
            fire = schedules.list_fires(record.id)[0]
            assert fire.status == "launch_failed" and fire.error_code == "schedule_launch_timed_out"
            assert fire.run_id is None and store.list_runs() == []
            assert await service.project_fires() == {
                "examined": 0,
                "projected": 0,
                "unavailable": 0,
            }

    asyncio.run(scenario())


def test_engine_time_zone_and_catchup_window_after_restart(stores, tmp_path):
    async def scenario():
        store, schedule_store, artifacts = stores
        filename = str(tmp_path / "temporal-catchup.sqlite")
        environment = await server(artifacts, dev_server_database_filename=filename)
        port = int(environment.client.service_client.config.target_host.rsplit(":", 1)[1])
        try:
            service = TemporalScheduleService(environment.client, schedule_store, task_queue(CORE))
            zone_record = await service.save(
                definition().model_copy(
                    update={"cron": "0 9 * * *", "time_zone": "Pacific/Auckland"}
                )
            )
            description = await environment.client.get_schedule_handle(
                engine_schedule_id(zone_record.id)
            ).describe()
            assert description.info.next_action_times
            assert all(
                instant.astimezone(ZoneInfo("Pacific/Auckland")).hour == 9
                for instant in description.info.next_action_times
            )
            periodic = definition().model_copy(
                update={
                    "cron": "* * * * * * *",
                    "paused": False,
                    "workflow_key": "fast",
                    "overlap_policy": "allow",
                    "catchup_window_seconds": 10,
                }
            )
            record = await service.save(periodic)
            async with worker(environment.client, store):

                async def fired():
                    return len(store.list_runs()) >= 1

                await until(fired)
            await environment.shutdown()
            await asyncio.sleep(13)
            environment = await server(artifacts, port=port, dev_server_database_filename=filename)
            service = TemporalScheduleService(environment.client, schedule_store, task_queue(CORE))
            async with worker(environment.client, store):
                handle = environment.client.get_schedule_handle(engine_schedule_id(record.id))

                async def missed():
                    return (await handle.describe()).info.num_actions_missed_catchup_window > 0

                await until(missed)
                assert (await handle.describe()).schedule.policy.catchup_window == timedelta(
                    seconds=10
                )
                await service.delete(record.id)
                await service.delete(zone_record.id)
        finally:
            await environment.shutdown()

    asyncio.run(scenario())

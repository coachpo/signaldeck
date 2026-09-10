"""Personal metadata and attention reads preserve execution facts and update identities."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.domain.execution import ExecutionEvidence
from app.domain.schedules import ScheduleDefinition, ScheduleFireRecord
from app.infrastructure.attention_store import AttentionStore
from app.infrastructure.platform_models import CommandRow, EvidenceRow, RunRow
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.result_metadata_store import AttentionReceiptRow, ResultMetadataRow
from app.infrastructure.schedule_store import ScheduleStore
from tests import test_task_experience
from tests.test_task_experience import configured

platform = test_task_experience.platform


def launch(client, store, identity="one"):
    response = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "parameters": {"text": identity},
            "launchId": identity,
        },
    )
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]
    store.project_run(run_id, "succeeded", {"confirmed": identity})
    return run_id


def test_exact_patch_conflict_persistence_and_immutable_execution(platform):
    client, store, _ = platform
    configured(client, store)
    run_id = launch(client, store)
    path = f"/api/runs/{run_id}/metadata"
    original = client.get(f"/api/runs/{run_id}").json()
    assert client.get(path).json()["revision"] == 0
    with store.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ResultMetadataRow)) == 0
    favorite = client.patch(path, json={"expectedRevision": 0, "isFavorite": True})
    assert favorite.status_code == 200, favorite.text
    note = client.patch(path, json={"expectedRevision": 1, "note": "Personal note"})
    assert note.status_code == 200
    assert note.json()["isFavorite"] is True and note.json()["isRead"] is False
    stale = client.patch(path, json={"expectedRevision": 1, "note": "lost update"})
    assert stale.status_code == 409
    assert client.get(path).json()["note"] == "Personal note"
    read = client.patch(path, json={"expectedRevision": 2, "isRead": True})
    assert read.status_code == 200
    assert client.get("/api/attention").json()["items"] == []
    assert client.get("/api/attention", params={"view": "all"}).json()["items"][0]["isRead"]
    cleared = client.patch(path, json={"expectedRevision": 3, "note": ""})
    assert cleared.json()["isFavorite"] and cleared.json()["isRead"]
    assert client.get(f"/api/runs/{run_id}").json() == original
    from app.infrastructure.result_metadata_store import ResultMetadataStore

    assert ResultMetadataStore(PlatformStore(store.session_factory)).get(run_id).revision == 4
    for payload in (
        {"expectedRevision": 4},
        {"expectedRevision": 4, "note": None},
        {"expectedRevision": 4, "isRead": None},
        {"expectedRevision": 4, "status": "failed"},
    ):
        assert client.patch(path, json=payload).status_code == 422


def test_filters_apply_before_pagination_and_preserve_default_unread(platform):
    client, store, _ = platform
    configured(client, store)
    ids = [launch(client, store, str(i)) for i in range(4)]
    for run_id in ids[1:]:
        client.patch(
            f"/api/runs/{run_id}/metadata", json={"expectedRevision": 0, "isFavorite": True}
        )
    first = client.get(
        "/api/runs", params={"isFavorite": "true", "limit": 1, "sort": "created_asc"}
    ).json()
    assert first["total"] == 3 and first["items"][0]["id"] == ids[1]
    second = client.get(
        "/api/runs",
        params={
            "isFavorite": "true",
            "limit": 1,
            "offset": 1,
            "sort": "created_asc",
            "snapshotAt": first["snapshotAt"],
        },
    ).json()
    assert second["items"][0]["id"] == ids[2]
    assert client.get("/api/runs", params={"isRead": "false"}).json()["total"] == 4
    assert (
        client.get("/api/runs", params={"isFavorite": "false"}).json()["items"][0]["id"] == ids[0]
    )


def test_unknown_read_remains_visible_and_reconciliation_has_new_identity(platform):
    client, store, _ = platform
    configured(client, store)
    run_id = launch(client, store)
    store.record_evidence_batch(
        [
            ExecutionEvidence(
                id="owner-node", run_id=run_id, node_id="echo", kind="node", status="running"
            ),
            ExecutionEvidence(
                id="owner-agent",
                run_id=run_id,
                node_id="echo",
                kind="agent",
                parent_id="owner-node",
                status="running",
            ),
        ]
    )
    evidence = ExecutionEvidence(
        parent_id="owner-agent",
        id="logical-write",
        run_id=run_id,
        node_id="echo",
        kind="tool",
        status="unknown",
        finished_at=datetime.now(UTC),
    )
    store.record_evidence(evidence)
    first = client.get("/api/attention").json()["items"][0]
    assert first["hasUnknownEffects"]
    assert (
        client.patch(
            f"/api/attention/{first['id']}", json={"expectedRevision": 0, "isRead": True}
        ).status_code
        == 200
    )
    again = client.get("/api/attention").json()["items"][0]
    assert again["id"] == first["id"] and again["isRead"] and again["hasUnknownEffects"]
    marked = client.patch(
        f"/api/runs/{run_id}/metadata", json={"expectedRevision": 0, "isRead": True}
    )
    assert marked.status_code == 200
    assert client.get("/api/attention").json()["items"][0]["hasUnknownEffects"]
    assert (
        client.patch(
            f"/api/attention/{first['id']}", json={"expectedRevision": 0, "isRead": False}
        ).status_code
        == 409
    )
    store.record_evidence(evidence.model_copy(update={"finished_at": datetime.now(UTC)}))
    assert client.get("/api/attention").json()["items"][0]["id"] == first["id"]
    store.record_evidence(
        evidence.model_copy(update={"status": "succeeded", "finished_at": datetime.now(UTC)})
    )
    resolved = client.get("/api/attention").json()["items"][0]
    assert (
        resolved["id"] != first["id"]
        and not resolved["isRead"]
        and not resolved["hasUnknownEffects"]
    )
    assert (
        client.patch(
            f"/api/attention/{first['id']}", json={"expectedRevision": 1, "isRead": True}
        ).status_code
        == 409
    )
    restarted = AttentionStore(PlatformStore(store.session_factory)).list().items
    assert restarted[0].id == resolved["id"]


def test_fire_without_run_and_repeated_reads_are_side_effect_free(platform):
    client, store, _ = platform
    schedules = ScheduleStore(store.session_factory)
    schedules.initialize()
    schedule = schedules.save(
        ScheduleDefinition(
            name="Broken", cron="0 9 * * *", package_key="missing", workflow_key="main"
        )
    )
    now = datetime.now(UTC)
    fire = ScheduleFireRecord(
        trigger_id="fire-1",
        schedule_id=schedule.id,
        scheduled_at=now,
        engine_workflow_id="engine",
        engine_run_id="execution",
        status="launch_failed",
        error_code="package_not_found",
        updated_at=now,
    )
    schedules.fires.record(fire)
    first = client.get("/api/attention").json()
    assert first["historyScope"] == "all_current_records"
    assert first["items"][0]["runId"] is None
    assert first["items"][0]["scheduleId"] == schedule.id
    schedules.fires.record(fire.model_copy(update={"updated_at": datetime.now(UTC)}))
    assert (
        client.get("/api/attention").json() == first
        or client.get("/api/attention").json()["items"] == first["items"]
    )
    with store.session_factory() as session:
        for row_type in (RunRow, CommandRow, EvidenceRow, AttentionReceiptRow, ResultMetadataRow):
            assert session.scalar(select(func.count()).select_from(row_type)) == 0


def test_attention_pages_exclude_updates_after_watermark_and_use_safe_dag_category(platform):
    client, store, _ = platform
    configured(client, store)
    ids = [launch(client, store, str(i)) for i in range(3)]
    run_id = ids[0]
    with store.session_factory() as session, session.begin():
        row = session.get(RunRow, run_id)
        row.status, row.error_code = "failed", "workflow_nodes_failed"
    store.record_evidence_batch(
        [
            ExecutionEvidence(
                id="failed-node",
                run_id=run_id,
                node_id="echo",
                kind="node",
                status="failed",
                error_code="model_http_error",
            ),
            ExecutionEvidence(
                id="failed-agent",
                run_id=run_id,
                node_id="echo",
                kind="agent",
                parent_id="failed-node",
                status="failed",
            ),
            ExecutionEvidence(
                parent_id="failed-agent",
                id="failed-model",
                run_id=run_id,
                node_id="echo",
                kind="model",
                status="failed",
                error_code="model_http_error",
                metadata={"errorCategory": "quota"},
            ),
        ]
    )
    first = client.get("/api/attention", params={"limit": 2, "view": "all"}).json()
    second = client.get(
        "/api/attention",
        params={"limit": 2, "offset": 2, "view": "all", "snapshotAt": first["snapshotAt"]},
    ).json()
    assert first["total"] == second["total"] == 3
    all_items = first["items"] + second["items"]
    assert len({item["id"] for item in all_items}) == 3
    assert next(item for item in all_items if item["runId"] == run_id)["errorCategory"] == "quota"
    with store.session_factory() as session, session.begin():
        row = session.get(RunRow, ids[1])
        row.finished_at = datetime.now(UTC) + timedelta(seconds=1)
        model = session.get(EvidenceRow, "failed-model")
        model.payload = {**model.payload, "metadata": {"errorCategory": {"bad": "value"}}}
    projected = client.get(
        "/api/attention", params={"view": "all", "snapshotAt": first["snapshotAt"]}
    )
    assert projected.status_code == 200, projected.text
    assert projected.json()["total"] == 2
    assert (
        next(item for item in projected.json()["items"] if item["runId"] == run_id)["errorCategory"]
        is None
    )


def test_concurrent_first_patch_has_one_winner(platform):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.domain.execution import ApplicationError
    from app.infrastructure.result_metadata_store import ResultMetadataStore
    from app.schemas.result_metadata import ResultMetadataPatch

    client, store, _ = platform
    configured(client, store)
    run_id = launch(client, store)
    barrier = Barrier(2)

    def update(note):
        barrier.wait()
        try:
            return (
                ResultMetadataStore(store)
                .patch(run_id, ResultMetadataPatch(expected_revision=0, note=note))
                .note
            )
        except ApplicationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(update, ["first", "second"]))
    assert outcomes.count("result_metadata_conflict") == 1
    saved = ResultMetadataStore(store).get(run_id)
    assert saved.revision == 1 and saved.note in {"first", "second"}


def test_unknown_network_attempt_is_not_an_unknown_logical_effect(platform):
    client, store, _ = platform
    configured(client, store)
    run_id = launch(client, store)
    store.record_evidence_batch(
        [
            ExecutionEvidence(
                id="node", run_id=run_id, node_id="echo", kind="node", status="succeeded"
            ),
            ExecutionEvidence(
                id="agent",
                run_id=run_id,
                node_id="echo",
                kind="agent",
                parent_id="node",
                status="succeeded",
            ),
            ExecutionEvidence(
                id="model",
                run_id=run_id,
                node_id="echo",
                kind="model",
                parent_id="agent",
                status="succeeded",
            ),
            ExecutionEvidence(
                id="attempt",
                run_id=run_id,
                node_id="echo",
                kind="attempt",
                parent_id="model",
                status="unknown",
            ),
        ]
    )
    item = client.get("/api/attention").json()["items"][0]
    assert item["hasUnknownEffects"] is False

"""Presets survive reopening without becoming package/run/schedule ownership roots."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.platform_dependencies import get_platform_store
from app.infrastructure.platform_models import PackageRevisionRow, RunRow
from app.infrastructure.platform_store import PlatformStore
from app.main import create_app
from tests.test_platform_api import source


def client_for(store: PlatformStore) -> TestClient:
    app = create_app(init_database=False)
    app.dependency_overrides[get_platform_store] = lambda: store
    return TestClient(app)


def test_presets_persist_revalidate_and_do_not_modify_execution(
    session_factory: sessionmaker[Session],
) -> None:
    store = PlatformStore(session_factory)
    store.initialize()
    with client_for(store) as client:
        package = client.post("/api/workflow-packages", json={"manifestSource": source()}).json()
        payload = {
            "name": "Morning report",
            "packageKey": package["key"],
            "workflowKey": "main",
            "packageHash": package["packageHash"],
            "parameters": {"text": "Business input"},
            "isFavorite": True,
            "isPinned": True,
        }
        response = client.post("/api/task-presets", json=payload)
        assert response.status_code == 201, response.text
        saved = response.json()
        assert saved["validationStatus"] == "valid"
        assert saved["needsRevalidation"] is False
        identity = saved["id"]
    with client_for(PlatformStore(session_factory)) as client:
        assert client.get("/api/task-presets").json()["items"][0]["id"] == identity
        document = json.loads(source())
        document["workflows"]["main"]["inputSchema"]["properties"]["text"]["maxLength"] = 3
        response = client.patch(
            "/api/workflow-packages/api-package",
            json={
                "manifestSource": json.dumps(document),
            },
        )
        assert response.status_code == 200, response.text
        current_hash = response.json()["packageHash"]
        saved = client.get(f"/api/task-presets/{identity}").json()
        assert saved["parameters"] == {"text": "Business input"}
        assert saved["packageHash"] == payload["packageHash"]
        assert saved["currentPackageHash"] == current_hash
        assert saved["needsRevalidation"] is True
        assert saved["validationStatus"] == "invalid"
        replacement = {
            key: payload[key]
            for key in (
                "name",
                "packageHash",
                "parameters",
                "isFavorite",
                "isPinned",
            )
        }
        assert client.put(f"/api/task-presets/{identity}", json=replacement).status_code == 409
        replacement.update(packageHash=current_hash, parameters={"text": "yes"})
        updated = client.put(f"/api/task-presets/{identity}", json=replacement)
        assert updated.status_code == 200, updated.text
        assert updated.json()["needsRevalidation"] is False
        assert client.delete(f"/api/task-presets/{identity}").status_code == 204
        assert client.get(f"/api/task-presets/{identity}").status_code == 404
        assert client.get("/api/workflow-packages/api-package").status_code == 200
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PackageRevisionRow)) == 2
        assert session.scalar(select(func.count()).select_from(RunRow)) == 0


def test_closed_inputs_bookmarks_and_credentials(session_factory: sessionmaker[Session]) -> None:
    store = PlatformStore(session_factory)
    store.initialize()
    with client_for(store) as client:
        package = client.post("/api/workflow-packages", json={"manifestSource": source()}).json()
        payload = {
            "name": "Bookmark",
            "packageKey": package["key"],
            "workflowKey": "main",
            "packageHash": package["packageHash"],
            "isFavorite": True,
        }
        bookmark = client.post("/api/task-presets", json=payload)
        assert bookmark.status_code == 201
        assert bookmark.json()["validationStatus"] == "not_applicable"
        for parameters in ({"text": "yes", "extra": 3}, {}, {"password": "sensitive-value"}):
            response = client.post("/api/task-presets", json={**payload, "parameters": parameters})
            assert response.status_code == 422, response.text
            assert "sensitive-value" not in response.text
        assert (
            client.post("/api/task-presets", json={**payload, "credentials": {}}).status_code == 422
        )
        assert len(client.get("/api/task-presets").json()["items"]) == 1


@pytest.mark.parametrize(
    ("schema", "parameters"),
    [
        ({"type": "array", "items": {"type": "string"}}, ["kept", "input"]),
        ({"type": "string"}, "kept input"),
        ({"type": "number"}, 12.5),
        ({"type": "boolean"}, False),
        ({"type": "null"}, None),
    ],
)
def test_presets_preserve_all_json_roots_and_distinguish_bookmarks(
    session_factory, schema, parameters
):
    from app.infrastructure.task_preset_store import TaskPresetRow

    store = PlatformStore(session_factory)
    store.initialize()
    document = json.loads(source())
    document["workflows"]["main"]["inputSchema"] = schema
    document["workflows"]["main"]["nodes"]["echo"]["inputMapping"] = {"value": {"text": "fixed"}}
    with client_for(store) as client:
        created = client.post(
            "/api/workflow-packages", json={"manifestSource": json.dumps(document)}
        )
        assert created.status_code == 201, created.text
        package = created.json()
        base = {
            "name": "Generic input",
            "packageKey": package["key"],
            "workflowKey": "main",
            "packageHash": package["packageHash"],
        }
        saved = client.post(
            "/api/task-presets", json={**base, "parameters": parameters, "hasParameters": True}
        )
        assert saved.status_code == 201, saved.text
        identity = saved.json()["id"]
        assert saved.json()["hasParameters"] is True
        assert saved.json()["parameters"] == parameters
        assert saved.json()["validationStatus"] == "valid"
        bookmark = client.post("/api/task-presets", json={**base, "parameters": None})
        assert bookmark.status_code == 201, bookmark.text
        bookmark_id = bookmark.json()["id"]
        # The previous implementation stored all bookmarks as JSON null.
        with session_factory() as session:
            assert (
                session.scalar(
                    select(TaskPresetRow.parameters.is_(None)).where(
                        TaskPresetRow.id == bookmark_id
                    )
                )
                is False
            )
            if parameters is None:
                assert (
                    session.scalar(
                        select(TaskPresetRow.parameters.is_(None)).where(
                            TaskPresetRow.id == identity
                        )
                    )
                    is True
                )
    with client_for(PlatformStore(session_factory)) as client:
        reopened = client.get(f"/api/task-presets/{identity}").json()
        assert reopened["parameters"] == parameters and reopened["hasParameters"] is True
        assert reopened["validationStatus"] == "valid"
        legacy = client.get(f"/api/task-presets/{bookmark_id}").json()
        assert legacy["hasParameters"] is False and legacy["validationStatus"] == "not_applicable"
        update = {
            "name": "Now a bookmark",
            "packageHash": package["packageHash"],
            "hasParameters": False,
        }
        assert (
            client.put(f"/api/task-presets/{identity}", json=update).json()["hasParameters"]
            is False
        )
        restored = client.put(
            f"/api/task-presets/{identity}",
            json={**update, "hasParameters": True, "parameters": parameters},
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["parameters"] == parameters
        assert restored.json()["hasParameters"] is True

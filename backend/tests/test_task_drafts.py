"""Draft persistence preserves unfinished values and the original launch intent."""

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.platform_models import RunRow
from app.infrastructure.platform_store import PlatformStore
from tests.test_platform_api import source
from tests.test_task_presets import client_for


@pytest.mark.parametrize("parameters", [None, {}, "", [], [None, "", {}]])
def test_draft_roundtrip_conflict_and_identity(
    session_factory: sessionmaker[Session], parameters: object
) -> None:
    platform = PlatformStore(session_factory)
    platform.initialize()
    with client_for(platform) as client:
        package = client.post("/api/workflow-packages", json={"manifestSource": source()}).json()
        payload = {
            "revision": 0,
            "name": "Unfinished",
            "packageKey": package["key"],
            "workflowKey": "main",
            "packageHash": package["packageHash"],
            "parameters": parameters,
            "jsonText": '{"incomplete": [',
            "launchId": "stable-original",
        }
        saved = client.put("/api/task-drafts/draft-a", json=payload)
        assert saved.status_code == 200, saved.text
        assert saved.json()["parameters"] == parameters
        assert saved.json()["jsonText"] == payload["jsonText"]
        assert saved.json()["revision"] == 1
        # Retrying after a lost save response is idempotent.
        assert client.put("/api/task-drafts/draft-a", json=payload).json()["revision"] == 1
        conflict = client.put("/api/task-drafts/draft-a", json={**payload, "name": "Other window"})
        assert conflict.status_code == 409
        pending = {
            **payload,
            "revision": 1,
            "jsonText": None,
            "pending": True,
            "bindingToken": "reviewed",
        }
        assert client.put("/api/task-drafts/draft-a", json=pending).json()["revision"] == 2
        assert (
            client.put(
                "/api/task-drafts/draft-a", json={**pending, "revision": 2, "parameters": "changed"}
            ).status_code
            == 409
        )
    with client_for(PlatformStore(session_factory)) as client:
        restored = client.get("/api/task-drafts/draft-a").json()
        assert restored["launchId"] == "stable-original"
        assert restored["pending"] is True
        assert restored["parameters"] == parameters
        assert client.delete("/api/task-drafts/draft-a?revision=1").status_code == 409
        assert client.delete("/api/task-drafts/draft-a?revision=2").status_code == 409
        released = {**pending, "revision": 2, "pending": False, "bindingToken": None}
        assert client.put("/api/task-drafts/draft-a", json=released).status_code == 200
        assert client.delete("/api/task-drafts/draft-a?revision=3").status_code == 204
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(RunRow)) == 0


def test_drafts_preserve_missing_and_schema_revision_and_reject_credentials(
    session_factory: sessionmaker[Session],
) -> None:
    platform = PlatformStore(session_factory)
    platform.initialize()
    with client_for(platform) as client:
        package = client.post("/api/workflow-packages", json={"manifestSource": source()}).json()
        payload = {
            "revision": 0,
            "name": "No applied input",
            "packageKey": package["key"],
            "workflowKey": "main",
            "packageHash": package["packageHash"],
            "hasParameters": False,
            "launchId": "original",
        }
        assert client.put("/api/task-drafts/absent", json=payload).status_code == 200
        assert (
            client.put(
                "/api/task-drafts/bad-source", json={**payload, "sourceRunId": "missing-run"}
            ).status_code
            == 422
        )
        document = json.loads(source())
        document["workflows"]["main"]["inputSchema"]["properties"]["text"]["maxLength"] = 2
        client.patch(
            "/api/workflow-packages/api-package", json={"manifestSource": json.dumps(document)}
        )
        restored = client.get("/api/task-drafts/absent").json()
        assert restored["hasParameters"] is False
        assert restored["needsRevalidation"] is True
        assert restored["packageHash"] == package["packageHash"]
        for unsafe in [
            dict(parameters={"apiKey": "never-echo"}, hasParameters=True),
            dict(jsonText='{"password": "never-echo"'),
        ]:
            response = client.put("/api/task-drafts/unsafe", json={**payload, **unsafe})
            assert response.status_code == 422
            assert "never-echo" not in response.text
        assert (
            client.put("/api/task-drafts/unknown", json={**payload, "credentials": {}}).status_code
            == 422
        )

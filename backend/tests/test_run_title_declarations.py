"""Frozen title declarations drive both result reads and database-wide ordering."""

import json

from tests.test_platform_api import release, source
from tests.test_task_experience import platform as platform


def test_history_title_selection_uses_frozen_declarations_not_business_aliases(platform):
    client, store, _ = platform
    store.install_plugin("example/echo", release())
    definition = json.loads(source())
    workflow = definition["workflows"]["main"]
    workflow["name"] = "Frozen fallback"
    workflow["inputSchema"] = {
        "type": "object",
        "properties": {
            "payload": {
                "type": "object",
                "properties": {"caption": {"type": "string"}},
                "required": ["caption"],
            },
            "title": {"type": "string"},
            "question": {"type": "string"},
        },
        "required": ["payload"],
    }
    workflow["nodes"]["echo"]["inputMapping"] = {
        "object": {"text": {"ref": "workflow.input.payload.caption"}}
    }
    workflow["presentation"] = {
        "version": "signaldeck.presentation/1",
        "title": {"kind": "input", "ref": "workflow.input.payload.caption"},
    }
    saved = client.post("/api/workflow-packages", json={"manifestSource": json.dumps(definition)})
    assert saved.status_code == 201, saved.text
    ids = []
    for index, caption in enumerate(("  Zulu  ", "Alpha", "   ")):
        response = client.post(
            "/api/workflow-packages/api-package/launches",
            json={
                "workflowKey": "main",
                "launchId": f"declared-{index}",
                "parameters": {
                    "payload": {"caption": caption},
                    "title": "Ignored title alias",
                    "question": "Ignored question alias",
                },
            },
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    workflow["presentation"]["title"] = {"kind": "static", "text": "  Beta static  "}
    changed = client.patch(
        "/api/workflow-packages/api-package", json={"manifestSource": json.dumps(definition)}
    )
    assert changed.status_code == 200, changed.text
    response = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "launchId": "static",
            "parameters": {"payload": {"caption": "Not the run title"}},
        },
    )
    assert response.status_code == 201, response.text
    ids.append(response.json()["id"])
    page = client.get("/api/runs", params={"sort": "title_asc"})
    assert page.status_code == 200, page.text
    assert [(r["id"], r["title"]) for r in page.json()["items"]] == [
        (ids[1], "Alpha"),
        (ids[3], "Beta static"),
        (ids[2], "Frozen fallback"),
        (ids[0], "Zulu"),
    ]
    for index, query in ((0, "Zulu"), (1, "Alpha"), (3, "Beta static")):
        result = client.get("/api/runs", params={"q": query}).json()
        assert [r["id"] for r in result["items"]] == [ids[index]]
        assert client.get(f"/api/runs/{ids[index]}/result").json()["title"] == query
    assert client.get("/api/runs", params={"q": "Ignored title alias"}).json()["total"] == 0


def test_undeclared_title_and_question_are_ordinary_input(platform):
    client, store, _ = platform
    store.install_plugin("example/echo", release())
    definition = json.loads(source())
    workflow = definition["workflows"]["main"]
    workflow["name"] = "Undeclared task"
    workflow["inputSchema"]["properties"].update(
        {"title": {"type": "string"}, "question": {"type": "string"}}
    )
    workflow["nodes"]["echo"]["inputMapping"] = {"object": {"text": {"ref": "workflow.input.text"}}}
    response = client.post(
        "/api/workflow-packages", json={"manifestSource": json.dumps(definition)}
    )
    assert response.status_code == 201, response.text
    response = client.post(
        "/api/workflow-packages/api-package/launches",
        json={
            "workflowKey": "main",
            "launchId": "undeclared",
            "parameters": {
                "text": "plain",
                "title": "No title magic",
                "question": "No question magic",
            },
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["title"] == "Undeclared task"
    assert client.get("/api/runs", params={"q": "No title magic"}).json()["total"] == 0
    assert client.get("/api/runs", params={"q": "Undeclared task"}).json()["total"] == 1

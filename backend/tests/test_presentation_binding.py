"""Preparation and launch bind presentation links to the captured tool release."""

import json

import pytest

from app.domain.tool_contracts import ToolDefinition, tool_contract_digest
from tests import test_platform_api
from tests.test_platform_api import release, source

platform = test_platform_api.platform


def install(client, store, *, key="item", page=True, declared=True):
    definition = json.loads(source())
    if declared:
        definition["workflows"]["main"]["presentation"] = {
            "version": "signaldeck.presentation/1",
            "sections": [
                {
                    "kind": "link",
                    "ref": "nodes.echo.output",
                    "label": "Details",
                    "toolId": "example/echo/copy",
                    "linkKey": "item",
                    "required": False,
                }
            ],
        }
    response = client.post(
        "/api/workflow-packages", json={"manifestSource": json.dumps(definition)}
    )
    assert response.status_code == 201
    plugin = release()
    if key is not None:
        plugin["tools"][0]["resultLinks"] = [
            {
                "version": "signaldeck.resultLink/1",
                "key": key,
                "label": "Details",
                "path": "items",
                "query": {"id": "tool.output.text"},
            }
        ]
    plugin["contractDigest"] = tool_contract_digest(
        tuple(ToolDefinition.model_validate(t) for t in plugin["tools"])
    )
    if page:
        plugin["pageUrl"] = "https://offline.invalid/app"
    store.install_plugin("example/echo", plugin)
    return plugin


@pytest.mark.parametrize(
    "key,page,code",
    [
        (None, True, "presentation_link_unavailable"),
        ("other", True, "presentation_link_unavailable"),
        ("item", False, "presentation_page_unavailable"),
    ],
)
def test_invalid_link_binding_blocks_preparation_and_launch_without_runs(platform, key, page, code):
    client, store, _ = platform
    install(client, store, key=key, page=page)
    parameters = {"workflowKey": "main", "parameters": {"text": "record"}}
    prepared = client.post("/api/workflow-packages/api-package/prepare", json=parameters)
    assert prepared.status_code == 200
    assert prepared.json()["ready"] is False
    assert prepared.json()["bindingToken"] is None
    assert code in prepared.json()["issues"]
    launched = client.post("/api/workflow-packages/api-package/launches", json=parameters)
    assert launched.status_code == 400
    assert launched.json()["code"] == code
    assert store.list_runs() == []


def test_link_release_is_frozen_and_idempotent_retry_ignores_current_plugin(platform):
    client, store, _ = platform
    plugin = install(client, store)
    parameters = {"workflowKey": "main", "parameters": {"text": "record"}, "launchId": "same"}
    prepared = client.post(
        "/api/workflow-packages/api-package/prepare",
        json={key: value for key, value in parameters.items() if key != "launchId"},
    ).json()
    assert prepared["ready"] is True
    parameters["bindingToken"] = prepared["bindingToken"]
    launched = client.post("/api/workflow-packages/api-package/launches", json=parameters)
    assert launched.status_code == 201
    run_id = launched.json()["id"]
    frozen = client.get(f"/api/runs/{run_id}").json()["spec"]["pluginReleases"][0]
    assert frozen["tools"][0]["resultLinks"] == plugin["tools"][0]["resultLinks"]
    store.set_plugin_enabled("example/echo", False)
    retried = client.post("/api/workflow-packages/api-package/launches", json=parameters)
    assert retried.status_code == 201 and retried.json()["id"] == run_id
    assert len(store.list_runs()) == 1


def test_undeclared_historical_package_does_not_require_plugin_page_or_links(platform):
    client, store, _ = platform
    install(client, store, declared=False, key=None, page=False)
    parameters = {"workflowKey": "main", "parameters": {"text": "record"}}
    assert client.post("/api/workflow-packages/api-package/prepare", json=parameters).json()[
        "ready"
    ]
    assert (
        client.post("/api/workflow-packages/api-package/launches", json=parameters).status_code
        == 201
    )

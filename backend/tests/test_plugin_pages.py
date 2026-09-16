"""Mounted page discovery stays offline and bound to immutable releases."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.plugin_pages import PluginMountRegistry
from app.domain.tool_contracts import PluginRelease, canonical_digest, tool_contract_digest
from app.infrastructure.platform_store import PlatformStore


def release(digit: str = "a", mount: str = "third-v1") -> dict[str, Any]:
    return {
        "pluginId": "example/third",
        "releaseId": digit,
        "artifactDigest": "sha256:" + digit * 64,
        "endpoint": "http://unavailable.invalid/mcp",
        "pageUrl": f"/apps/{mount}/",
        "tools": [],
        "contractDigest": tool_contract_digest(()),
        "ui": {"version": "signaldeck.pluginUi/1", "title": "Third party"},
    }


def test_ui_omission_preserves_release_serialization_and_digest() -> None:
    payload = release()
    payload.pop("ui")
    payload["pageUrl"] = "http://legacy.invalid/ui/"
    old = {
        **payload,
        "protocolVersion": "2025-11-25",
        "configSchema": {"type": "object"},
        "supportsOperationQuery": False,
        "supportsOperationDeduplication": False,
    }
    assert PluginRelease.model_validate(payload).model_dump(mode="json", by_alias=True) == old
    assert canonical_digest(
        PluginRelease.model_validate(old).model_dump(mode="json", by_alias=True)
    ) == canonical_digest(old)
    assert PluginRelease.model_validate(release()).contract_digest == old["contractDigest"]
    for ui in (
        None,
        {"version": "wrong", "title": "x"},
        {"version": "signaldeck.pluginUi/1", "title": " "},
        {"version": "signaldeck.pluginUi/1", "title": "x", "url": "x"},
    ):
        with pytest.raises(ValidationError):
            PluginRelease.model_validate({**payload, "ui": ui})


@pytest.mark.parametrize(
    "field,value",
    [
        ("mountKey", "../evil"),
        ("mountKey", "a/b"),
        ("upstream", "http://host;include"),
        ("upstream", "http://user:secret@host"),
        ("upstream", "http://host/path"),
        ("artifactDigest", "latest"),
    ],
)
def test_registry_rejects_unsafe_bindings(field: str, value: str) -> None:
    mount = {
        "mountKey": "third-v1",
        "pluginId": "example/third",
        "artifactDigest": "sha256:" + "a" * 64,
        "upstream": "http://third:8000",
    }
    with pytest.raises(ValidationError):
        PluginMountRegistry.model_validate(
            {"version": "signaldeck.pluginMounts/1", "mounts": [{**mount, field: value}]}
        )


def test_directory_keeps_historical_and_disabled_pages(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = PlatformStore(session_factory)
    old, new = release(), release("b", "third-v2")
    for descriptor in (old, new):
        store.install_plugin("example/third", descriptor)
    mounts = [
        {
            "mountKey": key,
            "pluginId": "example/third",
            "artifactDigest": "sha256:" + digit * 64,
            "upstream": "http://offline:8000",
        }
        for key, digit in (("third-v1", "a"), ("third-v2", "b"), ("not-installed", "c"))
    ]
    path = tmp_path / "mounts.json"
    path.write_text(json.dumps({"version": "signaldeck.pluginMounts/1", "mounts": mounts}))
    monkeypatch.setenv("SIGNALDECK_PLUGIN_MOUNTS_FILE", str(path))
    response = client.get("/api/plugin-pages")
    assert response.status_code == 200
    pages = response.json()
    assert [(item["mountKey"], item["enabled"]) for item in pages] == [
        ("third-v1", False),
        ("third-v2", True),
    ]
    assert pages[0]["pageUrl"] == "/apps/third-v1/"
    assert "upstream" not in response.text
    store.set_plugin_enabled("example/third", False)
    assert all(not item["enabled"] for item in client.get("/api/plugin-pages").json())
    mounts[0]["mountKey"] = "wrong-mount"
    path.write_text(json.dumps({"version": "signaldeck.pluginMounts/1", "mounts": mounts}))
    assert len(client.get("/api/plugin-pages").json()) == 1
    path.write_text('{"version":"invalid","secret":"do-not-expose"}')
    response = client.get("/api/plugin-pages")
    assert response.status_code == 503
    assert "do-not-expose" not in response.text

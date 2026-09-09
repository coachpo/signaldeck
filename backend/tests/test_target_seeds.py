"""Demo, bundled artifact and current plugin contract consistency."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.definitions import canonical_source, save_definition
from app.domain.compiler import validate_agent_tool_contract
from app.domain.mappings import evaluate_condition, resolve_mapping
from app.domain.schema_contract import validate_value
from app.infrastructure.package_seeds import load_seed_packages, seed_packages
from app.infrastructure.platform_store import PlatformStore

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo"


@pytest.fixture()
def store(database_url: str):
    engine = create_engine(database_url)
    result = PlatformStore(sessionmaker(engine, expire_on_commit=False))
    result.initialize()
    yield result
    engine.dispose()


def test_bundled_sources_hashes_and_plans_match_importable_examples() -> None:
    contracts = json.loads((DEMO / "contracts.json").read_text())
    seeds = load_seed_packages(DEMO)
    assert len(seeds) == 3
    assert set(contracts) == {seed.compiled.package.metadata.key for seed in seeds}
    for seed in seeds:
        compiled = seed.compiled
        key = compiled.package.metadata.key
        assert seed.source == (DEMO / f"{key}.yaml").read_text()
        assert compiled.content_hash == contracts[key]["contentHash"]
        assert {
            name: plan.model_dump(mode="json", by_alias=True)
            for name, plan in compiled.plans.items()
        } == contracts[key]["plans"]
        assert (
            sorted({tool for agent in compiled.package.agents.values() for tool in agent.tools})
            == contracts[key]["tools"]
        )
        assert (
            sorted({ref for agent in compiled.package.agents.values() for ref in agent.resources})
            == contracts[key]["resources"]
        )
        assert all(not agent.tool_cache for agent in compiled.package.agents.values())
        assert "apiKey" not in seed.source
        assert "http://" not in seed.source
        assert "https://" not in seed.source


def test_seed_loading_has_no_plugin_or_network_dependency(monkeypatch) -> None:
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("Seed loading cannot contact an external dependency")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    before = set(sys.modules)
    load_seed_packages(DEMO)
    assert not any(
        name.startswith(("finance_plugin", "oracle_plugin", "notes_plugin"))
        for name in set(sys.modules) - before
    )


def test_seed_install_is_atomic_and_preserves_operator_revisions(store: PlatformStore) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: seed_packages(store, DEMO), range(2)))
    assert sum(item["status"] == "created" for items in results for item in items) == 3
    assert len(store.list_packages()) == 3
    seed = load_seed_packages(DEMO)[0]
    key = seed.compiled.package.metadata.key
    initial = store.get_package(key)
    assert initial is not None
    # A no-op edit of the source returned by GET shares the same immutable revision.
    saved = save_definition(store, initial["source"], expected_key=key)
    assert saved["packageHash"] == initial["packageHash"]
    definition = saved["definition"]
    definition["metadata"]["description"] = "Operator-owned custom research workflow"
    updated = save_definition(store, canonical_source(definition), expected_key=key)
    assert updated["packageHash"] != initial["packageHash"]
    assert all(item["status"] == "preserved" for item in seed_packages(store, DEMO))
    assert store.get_package(key) == updated
    assert store.get_package(key, initial["packageHash"]) == initial


def test_seed_definitions_resolve_against_published_plugin_contracts() -> None:
    # This separate contract test reads each artifact's descriptor without entering
    # its lifespan or connecting a database. Core seed loading never imports plugins.
    script = """
import json
from finance_plugin.main import create_app as finance
from notes_plugin.main import create_app as notes
from oracle_plugin.main import app as oracle
database = 'postgresql+psycopg://unused:unused@127.0.0.1/unused'
apps = [finance(database), notes(database), oracle]
tools = {}
for app in apps:
    endpoint = next(
        route.endpoint for route in app.routes if getattr(route, 'path', None) == '/release'
    )
    descriptor = endpoint()
    tools.update({tool['toolId']: tool for tool in descriptor['tools']})
print(json.dumps(tools))
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        str(ROOT / "plugins" / path) for path in ("finance", "digital_oracle", "notes", "runtime")
    )
    result = subprocess.run(
        [sys.executable, "-c", script], env=environment, check=True, text=True, capture_output=True
    )
    contracts = json.loads(result.stdout)
    for seed in load_seed_packages(DEMO):
        for agent in seed.compiled.package.agents.values():
            for tool_id in agent.tools:
                assert tool_id in contracts
                assert set(contracts[tool_id]["resourceRequirements"]) <= set(agent.resources)
            if agent.strategy.kind == "deterministic":
                tool = contracts[agent.strategy.tool_id]
                validate_agent_tool_contract(agent, tool["inputSchema"], tool["outputSchema"])


def test_examples_preserve_parallelism_reuse_and_explicit_missing_semantics() -> None:
    packages = {
        seed.compiled.package.metadata.key: seed.compiled for seed in load_seed_packages(DEMO)
    }
    finance = packages["tradingagents_advisory_research"]
    workflow = finance.package.workflows["research"]
    plan = finance.plans["research"]
    assert plan.dependencies["opportunity"] == ["collect"]
    assert plan.dependencies["risk"] == ["collect"]
    assert workflow.nodes["opportunity"].uses == workflow.nodes["risk"].uses == "analyst"
    assert {source for edge in plan.edges for source in edge.sources} == {
        "control",
        "input",
        "condition",
    }
    condition = workflow.nodes["risk"].condition
    assert condition is not None
    namespace = {
        "workflow": {"input": {"question": "What is uncertain?", "includeRisk": False}},
        "nodes": {
            "collect": {"output": {"quotes": []}},
            "opportunity": {"output": {"text": "Limited evidence."}},
        },
    }
    assert evaluate_condition(condition, namespace) is False
    summary_input = resolve_mapping(workflow.nodes["summary"].input_mapping, namespace)
    assert summary_input["risk"]["text"] == "Risk review was not requested and was skipped."
    assert "risk" not in namespace["nodes"]
    notes = packages["research_notes"].package
    assert (
        notes.workflows["capture"].nodes["save"].uses
        == notes.workflows["research"].nodes["save"].uses
    )
    capture = notes.workflows["capture"]
    validate_value(capture.input_schema, {"title": "Experiment result", "text": "Observed outcome"})
    assert all(
        notes.agents[node.uses].strategy.kind == "deterministic" for node in capture.nodes.values()
    )


def test_optional_data_and_item_failures_do_not_prevent_import(store, tmp_path) -> None:
    assert load_seed_packages() == ()
    assert seed_packages(store) == []
    assert seed_packages(store, tmp_path / "absent") == []
    (tmp_path / "broken.yaml").write_text("not: [valid")
    (tmp_path / "valid.yml").write_text(load_seed_packages(DEMO)[0].source)
    results = seed_packages(store, tmp_path)
    assert [item["status"] for item in results] == ["error", "created"]
    assert len(store.list_packages()) == 1


def test_import_api_is_generic_and_uses_the_ordinary_revision_path(store) -> None:
    from fastapi.testclient import TestClient

    from app.api.platform_dependencies import get_platform_store
    from app.main import create_app

    app = create_app(init_database=False)
    app.dependency_overrides[get_platform_store] = lambda: store
    source = load_seed_packages(DEMO)[0].source
    with TestClient(app) as client:
        response = client.post(
            "/api/workflow-packages/import",
            json={
                "sources": [
                    {"name": "invalid", "manifestSource": "no: ["},
                    {"name": "valid", "manifestSource": source},
                ]
            },
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert [item["status"] for item in items] == ["error", "created"]
        key = items[1]["packageKey"]
        initial = store.get_package(key)
        assert initial is not None
        ordinary = save_definition(store, source)
        assert ordinary == initial
        changed = json.loads(json.dumps(initial["definition"]))
        changed["metadata"]["description"] = "An independently distributed definition"
        source = canonical_source(changed)
        payload = {"sources": [{"manifestSource": source}]}
        assert (
            client.post("/api/workflow-packages/import", json=payload).json()["items"][0]["status"]
            == "preserved"
        )
        assert store.get_package(key) == initial
        payload["mode"] = "update"
        assert (
            client.post("/api/workflow-packages/import", json=payload).json()["items"][0]["status"]
            == "updated"
        )
        assert store.get_package(key)["packageHash"] != initial["packageHash"]
        assert store.get_package(key, initial["packageHash"]) == initial


def test_missing_import_and_operator_save_share_atomic_identity_lock(store) -> None:
    from app.application.package_import import import_source

    source = load_seed_packages(DEMO)[0].source
    definition = load_seed_packages(DEMO)[0].compiled.package.model_dump(mode="json", by_alias=True)
    definition["metadata"]["description"] = "Concurrent operator revision"
    operator_source = canonical_source(definition)
    with ThreadPoolExecutor(max_workers=2) as pool:
        imported = pool.submit(import_source, store, source, missing_only=True)
        saved = pool.submit(save_definition, store, operator_source)
        assert imported.result()["status"] in {"created", "preserved"}
        operator = saved.result()
    assert store.get_package(operator["packageKey"]) == operator


@pytest.mark.parametrize("invalid_data", [False, True])
def test_api_starts_with_empty_or_invalid_optional_distribution(
    store, tmp_path, monkeypatch, invalid_data
) -> None:
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app import main
    from app.api.platform_dependencies import get_platform_store

    if invalid_data:
        (tmp_path / "invalid.yaml").write_text("invalid: [")
    settings = main.get_settings().model_copy(update={"workflow_data_dir": str(tmp_path)})
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_platform_store", lambda: store)
    monkeypatch.setattr(main, "get_schedule_store", lambda: store)
    monkeypatch.setattr(
        main, "get_core_artifacts", lambda: SimpleNamespace(current_digest=lambda: "fixed-core")
    )
    app = main.create_app()
    app.dependency_overrides[get_platform_store] = lambda: store
    with TestClient(app) as client:
        assert client.get("/api/workflow-packages").json() == {"items": []}
        source = load_seed_packages(DEMO)[0].source
        assert (
            client.post("/api/workflow-packages", json={"manifestSource": source}).status_code
            == 201
        )
    assert len(app.state.workflow_imports) == int(invalid_data)

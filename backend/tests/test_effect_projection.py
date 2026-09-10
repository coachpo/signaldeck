"""Historical uncertainty must not acquire a default read effect."""

import pytest

from app.application.effect_projection import unknown_evidence


@pytest.mark.parametrize(
    "tools",
    [
        [],
        [{"toolId": "p/read"}],
        [{"toolId": "p/read", "effect": "read"}, {"toolId": "p/read", "effect": "write"}],
    ],
)
def test_missing_or_ambiguous_frozen_effect_remains_conservative(tools):
    evidence = [{"id": "operation", "kind": "tool", "status": "unknown", "toolId": "p/read"}]
    assert unknown_evidence({"pluginReleases": [{"tools": tools}]}, evidence) == (["operation"], [])
    assert evidence[0]["status"] == "unknown"


def test_error_name_and_network_attempt_do_not_override_frozen_effect():
    spec = {"pluginReleases": [{"tools": [{"toolId": "p/save", "effect": "read"}]}]}
    evidence = [
        {
            "id": "read",
            "kind": "tool",
            "status": "unknown",
            "toolId": "p/save",
            "errorCode": "save_unknown",
        },
        {"id": "network", "kind": "attempt", "status": "unknown", "toolId": "p/write"},
    ]
    assert unknown_evidence(spec, evidence) == ([], ["read"])


def model_spec(grants):
    return {
        "workflowKey": "main",
        "definition": {
            "workflows": {"main": {"nodes": {"work": {"uses": "writer"}}}},
            "agents": {"writer": {"strategy": {"kind": "model"}, "tools": grants}},
        },
        "pluginReleases": [{"tools": [{"toolId": "p/write", "effect": "write"}]}],
    }


@pytest.mark.parametrize("kind", ["model", "agent", "node"])
def test_frozen_execution_without_tools_cannot_have_unknown_writes(kind):
    record = {"id": "uncertain", "kind": kind, "status": "unknown", "nodeId": "work"}
    assert unknown_evidence(model_spec([]), [record]) == ([], ["uncertain"])


def test_model_uncertainty_does_not_hide_actual_unknown_tool_write():
    records = [
        {"id": "model", "kind": "model", "status": "unknown", "nodeId": "work"},
        {"id": "tool", "kind": "tool", "status": "unknown", "toolId": "p/write"},
        {"id": "agent", "kind": "agent", "status": "unknown", "nodeId": "work"},
    ]
    assert unknown_evidence(model_spec(["p/write"]), records) == (["tool", "agent"], ["model"])


@pytest.mark.parametrize("effect", ["read", "write", None])
def test_agent_level_uncertainty_requires_complete_frozen_read_grants(effect):
    spec = model_spec(["p/write"])
    spec["pluginReleases"][0]["tools"][0]["effect"] = effect
    spec["definition"]["agents"]["writer"]["strategy"] = {
        "kind": "deterministic",
        "toolId": "p/write",
    }
    records = [{"id": "agent", "kind": "agent", "status": "unknown", "nodeId": "work"}]
    expected = ([], ["agent"]) if effect == "read" else (["agent"], [])
    assert unknown_evidence(spec, records) == expected


@pytest.mark.parametrize("missing", ["strategy", "tools"])
def test_missing_historical_agent_contract_is_not_defaulted_to_readonly(missing):
    spec = model_spec([])
    del spec["definition"]["agents"]["writer"][missing]
    records = [{"id": "old", "kind": "agent", "status": "unknown", "nodeId": "work"}]
    assert unknown_evidence(spec, records) == (["old"], [])


def test_missing_historical_model_strategy_remains_conservative():
    spec = model_spec([])
    del spec["definition"]["agents"]["writer"]["strategy"]
    records = [{"id": "old", "kind": "model", "status": "unknown", "nodeId": "work"}]
    assert unknown_evidence(spec, records) == (["old"], [])

"""Research package preserves collected evidence and has explicit monitor transitions."""

from pathlib import Path

import pytest

from app.domain.definition_parser import parse_package_source
from app.domain.mappings import evaluate_condition, resolve_mapping
from app.domain.schema_contract import validate_value

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def package():
    return parse_package_source((ROOT / "demo/us_equity_research.yaml").read_text()).package


def test_research_evidence_bypasses_every_model_and_saved_body_is_canonical(package):
    workflow = package.workflows["research"]
    original = {
        "evidenceId": "sec-original",
        "sourceId": "filing-accession",
        "url": "https://www.sec.gov/Archives/example.htm",
        "publicationDate": "2026-09-15",
        "locator": "Item 2, paragraph 4",
        "text": "Original evidence excerpt",
    }
    projection = {**original, "text": "Preview", "excerptTruncated": True}
    namespace = {
        "workflow": {
            "input": {
                "symbol": "NVDA",
                "asOfDate": "2026-09-16",
                "horizonMonths": 3,
                "question": "What can be verified?",
            }
        },
        "nodes": {
            "scope": {"output": {"cutoffAt": "2026-09-16T19:00:00Z"}},
            "collection": {
                "output": {
                    "evidence": [original],
                    "analysisEvidence": [projection],
                    "analysisContextTruncated": True,
                    "gaps": [],
                }
            },
            "decision": {
                "output": {
                    "content": "Unverified qualitative interpretation",
                    "claims": [],
                    "thresholds": [],
                }
            },
            "compile": {
                "output": {
                    "name": "Canonical research report",
                    "content": "Validated sections and original source appendix",
                }
            },
        },
    }
    for node in workflow.nodes.values():
        agent = package.agents[node.uses]
        if agent.strategy.kind == "model":
            assert not agent.tools
            arguments = resolve_mapping(node.input_mapping, namespace)
            assert arguments["evidence"] == [projection]
            assert arguments["analysisContextTruncated"] is True
            assert "supportingMaterials" not in arguments
            assert agent.input_schema["properties"]["evidence"]["maxItems"] == 64
    compiled = resolve_mapping(workflow.nodes["compile"].input_mapping, namespace)
    assert compiled["evidence"] == [original]
    assert compiled["narrative"] == namespace["nodes"]["decision"]["output"]["content"]
    saved = resolve_mapping(workflow.nodes["save"].input_mapping, namespace)
    assert saved == namespace["nodes"]["compile"]["output"]
    assert workflow.output_mapping["object"]["content"] == {"ref": "nodes.compile.output.content"}
    assert any(
        section.ref == "nodes.compile.output.content" for section in workflow.presentation.sections
    )


def test_collection_failure_preserves_gaps_and_optional_source_is_explicit(package):
    workflow = package.workflows["research"]
    namespace = {
        "workflow": {"input": {"symbol": "MSFT", "asOfDate": "2026-09-16"}},
        "nodes": {"scope": {"output": {"cutoffAt": "2026-09-16T19:00:00Z"}}},
    }
    assert not evaluate_condition(workflow.nodes["prediction_source"].condition, namespace)
    collected = resolve_mapping(workflow.nodes["collection"].input_mapping, namespace)
    assert collected["groups"] == [[], [], [], [], []]
    assert all(collected["gapGroups"][:4])
    assert collected["includePrediction"] is False
    assert collected["includeValuation"] is True
    assert collected["gapGroups"][4] == []
    validate_value(package.agents["merge_evidence"].input_schema, collected)
    compiled = resolve_mapping(workflow.nodes["compile"].input_mapping, namespace)
    assert compiled["evidence"] == []
    assert compiled["upstreamGaps"]
    assert compiled["claims"] == []
    assert compiled["thresholds"] == []
    validate_value(package.agents["compile_report"].input_schema, compiled)


@pytest.mark.parametrize(
    "state,should_research",
    [("invalid", False), ("unchanged", False), ("no_baseline", True), ("changed", True)],
)
def test_monitor_gates_all_deep_research_and_records_save_failure(package, state, should_research):
    workflow = package.workflows["monitor"]
    namespace = {
        "nodes": {
            "observe": {"output": {"state": state, "shouldResearch": should_research}},
            "compile": {"output": {"name": "Report", "content": "Canonical body"}},
        }
    }
    for key in (
        "market",
        "company",
        "macro",
        "news",
        "bull",
        "bear",
        "bull_reply",
        "bear_reply",
        "risk",
        "decision",
        "compile",
        "save",
    ):
        assert evaluate_condition(workflow.nodes[key].condition, namespace) is should_research
    assert not evaluate_condition(workflow.nodes["attach"].condition, namespace)
    assert (
        evaluate_condition(workflow.nodes["attach_failed"].condition, namespace) is should_research
    )
    namespace["nodes"]["save"] = {"output": {"reportId": 17}}
    assert evaluate_condition(workflow.nodes["attach"].condition, namespace) is should_research
    assert not evaluate_condition(workflow.nodes["attach_failed"].condition, namespace)


def test_monitor_dates_are_frozen_per_begin_not_schedule_input(package):
    monitor = package.workflows["monitor"]
    assert set(monitor.input_schema["properties"]) == {"monitorKey", "scope"}
    assert "asOfDate" not in monitor.input_schema["properties"]["scope"]["properties"]
    assert "cutoffAt" not in monitor.input_schema["properties"]["scope"]["properties"]
    namespace = {
        "workflow": {"input": {"scope": {"symbol": "NVDA", "cik": "0001045810"}}},
        "nodes": {
            "begin": {"output": {"asOfDate": "2026-09-17", "cutoffAt": "2026-09-17T18:00:00Z"}}
        },
    }
    for key in (
        "market_source",
        "financial_source",
        "document_source",
        "macro_source",
        "prediction_source",
    ):
        args = resolve_mapping(monitor.nodes[key].input_mapping, namespace)
        assert args["asOfDate"] == "2026-09-17"
        assert args["cutoffAt"] == "2026-09-17T18:00:00Z"


def test_macro_collection_retains_existing_five_series_without_model_tools(package):
    expected = ["CPIAUCSL", "CPILFESL", "A191RL1Q225SBEA", "UNRATE", "FEDFUNDS"]
    for key in ("research", "monitor"):
        workflow = package.workflows[key]
        namespace = {
            "workflow": {"input": {"asOfDate": "2026-09-16", "scope": {}}},
            "nodes": {
                "scope": {"output": {"cutoffAt": "2026-09-16T19:00:00Z"}},
                "begin": {"output": {"asOfDate": "2026-09-16", "cutoffAt": "2026-09-16T19:00:00Z"}},
            },
        }
        args = resolve_mapping(workflow.nodes["macro_source"].input_mapping, namespace)
        assert args["seriesIds"] == expected
        assert args["cutoffAt"] == "2026-09-16T19:00:00Z"
        assert package.agents[workflow.nodes["macro_source"].uses].strategy.kind == "deterministic"
        assert {
            "ref": "nodes.macro_source.output.evidence",
            "onMissing": {"value": []},
        } in workflow.nodes["collection"].input_mapping["object"]["groups"]["array"]


def test_monitor_skipped_dependencies_do_not_block_optional_save(package):
    workflow = package.workflows["monitor"]
    for key in (
        "market",
        "company",
        "macro",
        "news",
        "bull",
        "bear",
        "bull_reply",
        "bear_reply",
        "risk",
        "decision",
        "compile",
        "save",
        "attach",
        "attach_failed",
    ):
        assert "skipped" in workflow.nodes[key].accept_upstream_states
    namespace = {"nodes": {"observe": {"output": {"shouldResearch": True}}}}
    assert not evaluate_condition(workflow.nodes["save"].condition, namespace)
    assert evaluate_condition(workflow.nodes["attach_failed"].condition, namespace)


def test_monitor_stores_full_evidence_while_model_context_is_compact(package):
    for workflow in package.workflows.values():
        for node in workflow.nodes.values():
            if package.agents[node.uses].strategy.kind == "model":
                assert (
                    node.input_mapping["object"]["evidence"]["ref"]
                    == "nodes.collection.output.analysisEvidence"
                )
        assert (
            workflow.nodes["compile"].input_mapping["object"]["evidence"]["ref"]
            == "nodes.collection.output.evidence"
        )
    assert (
        package.workflows["monitor"].nodes["observe"].input_mapping["object"]["evidence"]["ref"]
        == "nodes.collection.output.evidence"
    )

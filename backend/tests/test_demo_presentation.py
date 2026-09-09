"""Example presentation is executable package data, including business-looking keys."""

from pathlib import Path

import pytest

from app.application.definitions import canonical_source
from app.domain.definition_parser import parse_package_source
from app.domain.mappings import evaluate_condition

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("package", "workflow", "title"),
    [
        ("tradingagents_advisory_research", "research", "市场研究"),
        ("digital_oracle_researcher", "research", "综合资料研究"),
        ("research_notes", "research", "整理笔记"),
        ("research_notes", "capture", "保存原文"),
    ],
)
def test_scenario_copy_and_presentation_survive_source_roundtrip(package, workflow, title):
    compiled = parse_package_source((ROOT / "demo" / f"{package}.yaml").read_text())
    definition = compiled.package.model_dump(mode="json", by_alias=True)
    scenario = definition["workflows"][workflow]
    assert scenario["name"] == title
    assert scenario["description"]
    assert all(spec["title"] for spec in scenario["inputSchema"]["properties"].values())
    assert scenario["presentation"]["version"] == "signaldeck.presentation/1"
    assert any(section["kind"] == "receipt" for section in scenario["presentation"]["sections"])
    assert parse_package_source(canonical_source(definition)).content_hash == compiled.content_hash


def test_market_risk_default_and_skip_are_declared_independently():
    compiled = parse_package_source(
        (ROOT / "demo/tradingagents_advisory_research.yaml").read_text()
    )
    workflow = compiled.package.workflows["research"]
    default = workflow.input_schema["properties"]["includeRisk"]
    assert default["x-signaldeck-schema"] == "signaldeck.schema/2"
    assert default["default"] is True
    sections = workflow.presentation.sections
    risk = next(section for section in sections if section.ref == "nodes.risk.output.text")
    assert risk.required is False
    assert (
        evaluate_condition(
            workflow.nodes["risk"].condition,
            {
                "workflow": {"input": {"includeRisk": False}},
                "nodes": {"collect": {"output": {"quotes": []}}},
            },
        )
        is False
    )


def test_unrelated_workflow_and_renamed_fields_keep_explicit_presentation():
    source = (Path(__file__).parent / "fixtures/dispatch_brief.yaml").read_text()
    original = parse_package_source(source)
    renamed = parse_package_source(
        source.replace("dispatch_brief", "harbor_update")
        .replace("briefing", "dispatch")
        .replace("headline", "subject")
        .replace("bulletin", "message")
        .replace("reportId", "reference")
        .replace("collection", "group")
        .replace("includeRisk", "appendix")
    )
    assert original.content_hash != renamed.content_hash
    for compiled in (original, renamed):
        definition = compiled.package.model_dump(mode="json", by_alias=True)
        assert (
            parse_package_source(canonical_source(definition)).content_hash == compiled.content_hash
        )
    workflow = original.package.workflows["briefing"]
    assert workflow.input_schema["properties"]["includeRisk"]["default"] is False
    assert [section.kind for section in workflow.presentation.sections] == [
        "markdown",
        "value",
        "value",
    ]

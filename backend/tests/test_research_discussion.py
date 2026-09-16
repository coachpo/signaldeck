"""Finance discussion integrity uses independent, minimal report arguments."""

import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

for directory in ("runtime", "finance"):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / directory))

from finance_plugin.research_evidence import ResearchReportInput, ResearchReportOutput  # noqa: E402
from plugin_runtime.serialization import model_wire_schema  # noqa: E402

from tests.test_research_evidence import compile_report, request  # noqa: E402


def discussion():
    def reference(argument_id, **fields):
        return {"argumentId": argument_id, **fields, "evidenceIds": ["actual"]}

    return {
        "bullCase": {"arguments": [reference("support", statement="Demand remains resilient.")]},
        "bearCase": {
            "arguments": [reference("concern", statement="Competition deserves attention.")]
        },
        "bullResponse": {
            "responses": [
                reference(
                    "concern", disposition="accepted", rationale="The concern remains material."
                )
            ]
        },
        "bearResponse": {
            "responses": [
                reference(
                    "support",
                    disposition="partially_accepted",
                    rationale="The source supports the premise.",
                )
            ]
        },
        "riskReview": {
            "assessments": [
                reference(key, assessment="supported", rationale="Monitor this premise.")
                for key in ("support", "concern")
            ]
        },
        "adjudication": {
            "decisions": [
                reference(key, disposition="retained", rationale="Retain with stated uncertainty.")
                for key in ("support", "concern")
            ]
        },
    }


def report_arguments():
    return {**request(), "discussion": discussion()}


def assert_incomplete(args):
    result = compile_report(args)
    assert result["status"] == "insufficient_evidence"
    assert result["dataGaps"]
    return result


def test_omitted_discussion_preserves_existing_report_output():
    result = compile_report(request())
    assert result["status"] == "validated"
    assert result["narrativeStatus"] == "absent"
    assert set(result) == {
        "name",
        "content",
        "status",
        "dataGaps",
        "evidence",
        "narrativeStatus",
        "independentSourceCount",
        "cutoffAt",
    }


def test_complete_discussion_is_rendered_without_promoting_model_claims():
    args = report_arguments()
    result = compile_report(args)
    assert result["status"] == "validated"
    assert result["dataGaps"] == []
    assert result["narrativeStatus"] == "unverified"
    assert set(result) == set(compile_report(request()))
    for stage in args["discussion"].values():
        for items in stage.values():
            for item in items:
                assert item["argumentId"] in result["content"]
                assert item.get("statement", item.get("rationale")) in result["content"]
    ResearchReportOutput.model_validate(result)


def test_unresolved_is_a_complete_explicit_outcome():
    args = report_arguments()
    for stage, collection, field in (
        ("bullResponse", "responses", "disposition"),
        ("riskReview", "assessments", "assessment"),
        ("adjudication", "decisions", "disposition"),
    ):
        args["discussion"][stage][collection][0][field] = "unresolved"
    result = compile_report(args)
    assert result["status"] == "validated"
    assert result["content"].count("未决（未核实）") == 3


@pytest.mark.parametrize("stage", list(discussion()))
def test_missing_stage_is_visible_in_gaps(stage):
    args = report_arguments()
    del args["discussion"][stage]
    assert_incomplete(args)


@pytest.mark.parametrize(
    "stage,collection",
    [
        ("bullCase", "arguments"),
        ("bullResponse", "responses"),
        ("riskReview", "assessments"),
        ("adjudication", "decisions"),
    ],
)
def test_missing_and_duplicate_coverage_is_rejected(stage, collection):
    args = report_arguments()
    items = args["discussion"][stage][collection]
    items.append(deepcopy(items[0]))
    assert_incomplete(args)
    args = report_arguments()
    args["discussion"][stage][collection].pop()
    assert_incomplete(args)


def test_argument_identity_is_unique_across_both_sides():
    args = report_arguments()
    args["discussion"]["bearCase"]["arguments"][0]["argumentId"] = "support"
    assert_incomplete(args)


@pytest.mark.parametrize(
    "stage,collection",
    [
        ("bullResponse", "responses"),
        ("bearResponse", "responses"),
        ("riskReview", "assessments"),
        ("adjudication", "decisions"),
    ],
)
def test_unknown_target_is_rejected(stage, collection):
    args = report_arguments()
    args["discussion"][stage][collection][0]["argumentId"] = "unknown"
    assert_incomplete(args)


@pytest.mark.parametrize("stage,target", [("bullResponse", "support"), ("bearResponse", "concern")])
def test_responses_must_address_the_opposing_case(stage, target):
    args = report_arguments()
    args["discussion"][stage]["responses"][0]["argumentId"] = target
    assert_incomplete(args)


@pytest.mark.parametrize(
    "stage,collection",
    [
        ("bullCase", "arguments"),
        ("bullResponse", "responses"),
        ("riskReview", "assessments"),
        ("adjudication", "decisions"),
    ],
)
@pytest.mark.parametrize("references", [["missing"]])
def test_every_discussion_item_requires_eligible_evidence(stage, collection, references):
    args = report_arguments()
    args["discussion"][stage][collection][0]["evidenceIds"] = references
    assert_incomplete(args)


def test_ineligible_evidence_cannot_support_discussion():
    args = report_arguments()
    args["claims"] = []
    args["evidence"][0]["verified"] = False
    result = assert_incomplete(args)
    assert any("引用的证据 actual 不可用于结构化校验" in gap for gap in result["dataGaps"])


@pytest.mark.parametrize(
    "stage,collection,field",
    [
        ("bullCase", "arguments", "statement"),
        ("bullResponse", "responses", "rationale"),
        ("riskReview", "assessments", "rationale"),
        ("adjudication", "decisions", "rationale"),
    ],
)
@pytest.mark.parametrize(
    "text", ["Gross margin was 73.8%", "毛利率七成", "低于指引", "revenue doubled two times"]
)
def test_discussion_cannot_bypass_numeric_validation(stage, collection, field, text):
    args = report_arguments()
    args["discussion"][stage][collection][0][field] = text
    result = assert_incomplete(args)
    assert text in result["content"]
    assert result["narrativeStatus"] == "unverified"


def test_nested_discussion_schema_is_closed_and_bounded():
    schema = model_wire_schema(ResearchReportInput)
    stages = schema["properties"]["discussion"]["properties"]
    for stage, collection, limit in (
        ("bullCase", "arguments", 3),
        ("bearCase", "arguments", 3),
        ("bullResponse", "responses", 3),
        ("bearResponse", "responses", 3),
        ("riskReview", "assessments", 6),
        ("adjudication", "decisions", 6),
    ):
        container = stages[stage]
        assert container["unevaluatedProperties"] is False
        array = container["properties"][collection]
        assert array["maxItems"] == limit
        item = array["items"]
        assert item["unevaluatedProperties"] is False
        assert item["properties"]["evidenceIds"]["maxItems"] == 10
        args = report_arguments()
        args["discussion"][stage][collection] *= limit + 1
        with pytest.raises(ValidationError):
            ResearchReportInput.model_validate(args)
    args = report_arguments()
    args["discussion"]["bullCase"]["arguments"][0]["metadata"] = {"extra": True}
    with pytest.raises(ValidationError):
        compile_report(args)


def test_qualitative_discussion_allows_explicit_empty_evidence_lists():
    args = report_arguments()
    for stage in args["discussion"].values():
        for items in stage.values():
            for item in items:
                item["evidenceIds"] = []
    assert compile_report(args)["status"] == "validated"


def test_empty_discussion_has_missing_stages_but_no_model_narrative():
    result = assert_incomplete({**request(), "discussion": {}})
    assert result["narrativeStatus"] == "absent"


@pytest.mark.parametrize("stage", list(discussion()))
def test_empty_stage_mapping_is_reported_as_missing(stage):
    args = report_arguments()
    args["discussion"][stage] = {}
    result = assert_incomplete(args)
    assert any("未提供此阶段" in gap for gap in result["dataGaps"])


@pytest.mark.parametrize(
    "stage,collection,field,value",
    [
        ("bullCase", "arguments", "statement", "x" * 1001),
        ("bullCase", "arguments", "argumentId", "x" * 81),
        ("bullCase", "arguments", "evidenceIds", ["actual"] * 11),
        ("bullResponse", "responses", "disposition", "supported"),
        ("riskReview", "assessments", "assessment", "retained"),
        ("adjudication", "decisions", "disposition", "accepted"),
    ],
)
def test_discussion_rejects_invalid_typed_items(stage, collection, field, value):
    args = report_arguments()
    args["discussion"][stage][collection][0][field] = value
    with pytest.raises(ValidationError):
        compile_report(args)


def test_invalid_discussion_records_remain_in_report_for_inspection():
    args = report_arguments()
    args["discussion"]["bullResponse"]["responses"][0].update(
        argumentId="unmatched", rationale="Explicit unsupported response."
    )
    result = assert_incomplete(args)
    assert "unmatched" in result["content"]
    assert "Explicit unsupported response." in result["content"]


def test_discussion_text_uses_existing_markdown_escaping():
    args = report_arguments()
    args["discussion"]["bullCase"]["arguments"][0][
        "statement"
    ] = "Source excerpt ``` <script> & observation"
    result = assert_incomplete(args)
    assert "&#96;&#96;&#96; &lt;script&gt; &amp; observation" in result["content"]

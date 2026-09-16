"""Research output must not inherit unsupported source or arithmetic claims."""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "finance"):
    sys.path.insert(0, str(PLUGINS / directory))

from finance_plugin.research_evidence import ResearchReportInput, ResearchReportOutput  # noqa: E402
from finance_plugin.research_report import compile_research_report  # noqa: E402
from finance_plugin.research_report_validation import day_end  # noqa: E402
from plugin_runtime.serialization import model_wire_schema  # noqa: E402

NOW = datetime(2026, 9, 16, 20, tzinfo=UTC)


def evidence(key="actual", value="73.8", **changes):
    return {
        "evidenceId": key,
        "sourceId": "official-filing",
        "kind": "fact",
        "title": "Gross margin",
        "url": "https://www.sec.gov/Archives/example.htm",
        "publishedAt": "2026-09-15T20:00:00Z",
        "retrievedAt": "2026-09-16T19:00:00Z",
        "periodStart": "2026-04-01",
        "periodEnd": "2026-06-30",
        "value": value,
        "unit": "%",
        "metric": "grossMargin",
        "locator": "Results, paragraph 2",
        "verified": True,
        **changes,
    }


def request():
    return {
        "symbol": "NVDA",
        "asOfDate": "2026-09-16",
        "cutoffAt": "2026-09-16T20:00:00Z",
        "evidence": [evidence()],
        "claims": [
            {
                "claimId": "actualClaim",
                "metric": "grossMargin",
                "evidenceIds": ["actual"],
                "value": "73.8",
                "unit": "%",
                "periodStart": "2026-04-01",
                "periodEnd": "2026-06-30",
            }
        ],
    }


def compile_report(value):
    return compile_research_report(value, now=NOW)


def test_guidance_range_and_hypothesis_are_distinct():
    args = request()
    args["evidence"] += [evidence("center", "74"), evidence("tolerance", "0.5")]
    args["thresholds"] = [
        {
            "thresholdId": "guidance",
            "basis": "guidance",
            "metric": "grossMargin",
            "unit": "%",
            "periodStart": "2026-04-01",
            "periodEnd": "2026-06-30",
            "lower": "73.5",
            "upper": "74.5",
            "evidenceIds": ["center", "tolerance"],
            "centerEvidenceId": "center",
            "toleranceEvidenceId": "tolerance",
            "observedEvidenceId": "actual",
        }
    ]
    result = compile_report(args)
    assert result["status"] == "validated"
    assert "区间内 (within)" in result["content"]
    assert result["independentSourceCount"] == 1
    args["thresholds"][0]["lower"] = "74"
    assert "bounds do not match" in " ".join(compile_report(args)["dataGaps"])
    args["thresholds"] = [
        {
            "thresholdId": "hypothesis",
            "basis": "hypothesis",
            "metric": "grossMargin",
            "unit": "%",
            "periodStart": "2026-04-01",
            "periodEnd": "2026-06-30",
            "lower": "74",
            "observedEvidenceId": "actual",
            "rationale": "Conservative operating assumption",
        }
    ]
    result = compile_report(args)
    assert "研究假设" in result["content"] and "低于下界" in result["content"]
    del args["thresholds"][0]["rationale"]
    with pytest.raises(ValidationError):
        ResearchReportInput.model_validate(args)
    assert any(
        "thresholds[1]: invalid structured item" in gap for gap in compile_report(args)["dataGaps"]
    )


@pytest.mark.parametrize(
    "field,value,gap",
    [
        ("evidenceIds", ["missing"], "missing or ineligible"),
        ("value", "73.9", "recomputation"),
        ("unit", "USD", "unit mismatch"),
        ("periodEnd", "2026-09-30", "period mismatch"),
        ("metric", "profit", "metric mismatch"),
        ("kind", "user", "not a verified fact"),
    ],
)
def test_rejects_unbacked_claims(field, value, gap):
    args = request()
    args["claims"][0][field] = value
    result = compile_report(args)
    assert result["status"] == "insufficient_evidence"
    assert any(gap in reason for reason in result["dataGaps"])


@pytest.mark.parametrize(
    "changes,gap",
    [
        ({"publishedAt": None}, "publication time unknown"),
        ({"publishedAt": "2026-09-16T20:00:00Z"}, "outside cutoff"),
        ({"locator": None}, "locator"),
        ({"verified": False}, "unverified source"),
        ({"symbol": "MSFT"}, "symbol differs"),
    ],
)
def test_source_eligibility(changes, gap):
    args = request()
    args["evidence"][0].update(changes)
    result = compile_report(args)
    assert result["status"] == "insufficient_evidence"
    assert any(gap in reason for reason in result["dataGaps"])
    assert result["evidence"][0]["evidenceId"] == "actual"


def test_date_precision_does_not_claim_intraday_knowledge():
    args = request()
    args["evidence"][0].pop("publishedAt")
    args["evidence"][0]["publicationDate"] = "2026-09-16"
    assert any("intraday" in gap for gap in compile_report(args)["dataGaps"])
    args["evidence"][0]["publicationDate"] = "2026-09-15"
    assert compile_report(args)["status"] == "validated"
    assert day_end(datetime(2026, 3, 8).date()).hour == 4
    assert day_end(datetime(2026, 1, 8).date()).hour == 5


@pytest.mark.parametrize(
    "narrative", ["Gross margin was 73.8%", "低于指引", "毛利率七成", "revenue doubled two times"]
)
def test_narrative_cannot_bypass_structured_numeric_check(narrative):
    args = request()
    args["narrative"] = narrative
    result = compile_report(args)
    assert result["status"] == "insufficient_evidence"
    assert result["narrativeStatus"] == "unverified"
    assert "模型推论，未经事实校验" in result["content"]


def test_qualitative_narrative_and_upstream_gaps():
    args = request()
    args["narrative"] = "竞争压力仍需持续关注。"
    assert compile_report(args)["status"] == "validated"
    args["upstreamGaps"] = ["optional social source unavailable"]
    assert compile_report(args)["dataGaps"] == args["upstreamGaps"]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e3", 73.8])
def test_decimal_input_is_a_finite_plain_string(value):
    args = request()
    args["claims"][0]["value"] = value
    with pytest.raises(ValidationError):
        ResearchReportInput.model_validate(args)
    result = compile_report(args)
    assert result["status"] == "insufficient_evidence"
    assert any("claims[1]: invalid structured item" in gap for gap in result["dataGaps"])


def test_user_materials_cannot_be_verified():
    args = request()
    args["evidence"][0]["kind"] = "user"
    with pytest.raises(ValidationError):
        compile_report(args)


def test_conflicting_identity_and_zero_division_are_not_silent():
    args = request()
    args["evidence"].append(evidence(value="74"))
    assert any("conflicting" in gap for gap in compile_report(args)["dataGaps"])
    args = request()
    args["evidence"].append(evidence("denominator", "0"))
    args["claims"][0].update(formula="percent", evidenceIds=["actual", "denominator"])
    assert any("zero denominator" in gap for gap in compile_report(args)["dataGaps"])


def test_source_appendix_preserves_every_field_and_markdown_fences():
    args = request()
    args["evidence"][0]["text"] = "Original excerpt ``` malicious fence"
    result = compile_report(args)
    assert "公开时间：2026-09-15 20:00:00+00:00" in result["content"]
    assert "https://www.sec.gov/Archives/example.htm" in result["content"]
    assert "Results, paragraph 2" in result["content"]
    assert "&#96;&#96;&#96;" in result["content"]
    ResearchReportOutput.model_validate(result)


def test_schemas_are_closed_without_dynamic_maps():
    for model in (ResearchReportInput, ResearchReportOutput):
        schema = model_wire_schema(model)

        def inspect(node):
            if node.get("type") == "object":
                assert node["unevaluatedProperties"] is False
                assert "additionalProperties" not in node
                for child in node["properties"].values():
                    inspect(child)
            if node.get("type") == "array":
                inspect(node["items"])

        inspect(schema)
    args = request()
    args["evidence"][0]["metadata"] = {"unknown": True}
    with pytest.raises(ValidationError):
        compile_report(args)


def test_derived_fact_is_recomputed_and_invalidity_propagates():
    args = request()
    args["evidence"] += [evidence("left", "74"), evidence("right", "0.2")]
    args["evidence"][0].update(formula="difference", inputEvidenceIds=["left", "right"])
    assert compile_report(args)["status"] == "validated"
    args["evidence"][0]["value"] = "74.2"
    assert any("derived value" in gap for gap in compile_report(args)["dataGaps"])
    args["evidence"][0].update(formula="identity", inputEvidenceIds=["actual"])
    assert any("cyclic" in gap for gap in compile_report(args)["dataGaps"])


def test_superseded_fact_stays_in_appendix_but_cannot_support_claim():
    args = request()
    args["evidence"].append(evidence("revised", "74", supersedesEvidenceId="actual"))
    result = compile_report(args)
    assert len(result["evidence"]) == 2
    assert any("ineligible" in gap for gap in result["dataGaps"])


def test_report_displays_known_gaps_and_metrics_as_readable_text():
    args = request()
    args["upstreamGaps"] = [
        "sec_filings_truncated",
        "document_size_limit",
        "metric_missing[short_term_debt]: No supported standard-taxonomy fact visible by cutoff.",
    ]
    result = compile_report(args)
    assert result["dataGaps"] == args["upstreamGaps"]
    for code in ("sec_filings_truncated", "document_size_limit", "metric_missing"):
        assert code not in result["content"]
    assert "短期债务" in result["content"]
    assert "毛利率" in result["content"]
    assert "SEC 申报列表达到本次采集上限" in result["content"]


def test_vintage_availability_bound_is_not_a_publication_time():
    args = request()
    args["evidence"][0].pop("publishedAt")
    args["evidence"][0]["availableByDate"] = "2026-09-15"
    result = compile_report(args)
    assert result["status"] == "validated"
    assert "公开时间：未知" in result["content"]
    assert "可确认可用日期上界：2026-09-15" in result["content"]
    assert "publishedAt" not in result["evidence"][0]
    args["evidence"][0]["availableByDate"] = "2026-09-16"
    assert any(
        "availability upper bound exceeds" in gap for gap in compile_report(args)["dataGaps"]
    )
    args["cutoffAt"] = "2026-09-16T04:00:00Z"
    args["evidence"][0]["availableByDate"] = "2026-09-15"
    assert compile_report(args)["status"] == "validated"
    args["cutoffAt"] = "2026-09-16T03:59:59Z"
    assert compile_report(args)["status"] == "insufficient_evidence"
    args["evidence"][0].pop("availableByDate")
    assert any("publication time unknown" in gap for gap in compile_report(args)["dataGaps"])


def test_comparison_is_retained_and_never_inherits_fact_verification():
    args = request()
    args["comparison"] = "较上次研究：竞争压力仍存。\n供给 & 需求需要继续跟踪。"
    result = compile_report(args)
    assert "较上次的变化（模型对比，未经事实校验）" in result["content"]
    assert "较上次研究：竞争压力仍存。\n供给 &amp; 需求需要继续跟踪。" in result["content"]
    assert result["status"] == "validated"
    assert result["narrativeStatus"] == "unverified"
    args["comparison"] = "较上次毛利率增加 2%。"
    result = compile_report(args)
    assert args["comparison"] in result["content"]
    assert result["status"] == "insufficient_evidence"
    assert any("assertion in comparison" in gap for gap in result["dataGaps"])
    args["comparison"] = "x" * 4001
    with pytest.raises(ValidationError):
        compile_report(args)


def test_three_revision_archive_does_not_degrade_current_claim():
    args = request()
    args["evidence"] = [
        evidence("oldest", "70", verified=False),
        evidence("prior", "72", verified=False, supersedesEvidenceId="oldest"),
        evidence("actual", "73.8", supersedesEvidenceId="prior"),
    ]
    result = compile_report(args)
    assert result["status"] == "validated"
    assert result["dataGaps"] == []
    assert [item["evidenceId"] for item in result["evidence"]] == ["oldest", "prior", "actual"]
    assert "oldest" in result["content"] and "prior" in result["content"]
    args["claims"][0].update(evidenceIds=["oldest"], value="70")
    result = compile_report(args)
    assert result["status"] == "insufficient_evidence"
    assert any("missing or ineligible" in gap for gap in result["dataGaps"])
    args["claims"][0].update(evidenceIds=["actual"], value="73.8")
    args["evidence"].append(evidence("unverified", "80", verified=False))
    assert any("unverified: unverified source" in gap for gap in compile_report(args)["dataGaps"])

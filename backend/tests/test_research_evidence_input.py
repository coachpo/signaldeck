"""A malformed model assertion must not abort an otherwise reviewable report."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from tests.test_research_evidence import compile_report, request


@pytest.mark.parametrize(
    "changes",
    [
        {"value": "326.588 至 333.979"},
        {"periodEnd": "not-a-date"},
        {"unexpected": "private rejected payload"},
    ],
)
def test_bad_claim_is_excluded_without_losing_valid_claim(changes):
    args = request()
    bad = {**args["claims"][0], "claimId": "bad", **changes}
    args["claims"].append(bad)
    result = compile_report(args)
    assert result["status"] == "insufficient_evidence"
    assert any("claims[2]: invalid structured item" in gap for gap in result["dataGaps"])
    assert "毛利率：73.8 %" in result["content"]
    assert "326.588 至 333.979" not in result["content"]
    assert "not-a-date" not in result["content"]
    assert "private rejected payload" not in result["content"]
    assert not any("no validated numerical claims" in gap for gap in result["dataGaps"])


def test_bad_threshold_does_not_abort_valid_fact():
    args = request()
    args["thresholds"] = [
        {
            "thresholdId": "bad",
            "basis": "hypothesis",
            "metric": "grossMargin",
            "unit": "%",
            "periodEnd": "2026-06-30",
            "lower": "seventy four",
            "observedEvidenceId": "actual",
            "rationale": "Operating assumption",
        }
    ]
    result = compile_report(args)
    assert result["status"] == "insufficient_evidence"
    assert any("thresholds[1]: invalid structured item" in gap for gap in result["dataGaps"])
    assert "毛利率：73.8 %" in result["content"]
    assert "seventy four" not in result["content"]


@pytest.mark.parametrize("name,limit", [("claims", 100), ("thresholds", 50)])
def test_array_limits_still_apply_before_dropping_invalid_items(name, limit):
    args = request()
    args[name] = [{} for _ in range(limit + 1)]
    with pytest.raises(ValidationError):
        compile_report(args)
    args[name] = "invalid collection"
    with pytest.raises(ValidationError):
        compile_report(args)


@pytest.mark.parametrize("change", ["source", "outer", "date"])
def test_source_and_outer_contracts_remain_strict(change):
    args = deepcopy(request())
    if change == "source":
        args["evidence"][0]["value"] = "326.588 至 333.979"
    elif change == "outer":
        args["unsupported"] = True
    else:
        args["asOfDate"] = "not-a-date"
    with pytest.raises(ValidationError):
        compile_report(args)

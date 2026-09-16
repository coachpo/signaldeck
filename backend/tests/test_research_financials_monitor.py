# ruff: noqa: E402
"""Historical SEC revisions remain attributable without poisoning current coverage."""

import sys
from datetime import datetime
from pathlib import Path

for path in ("finance", "runtime"):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / path))


from finance_plugin.research_collection import ResearchMergeInput, merge_evidence
from finance_plugin.research_financials import lookup_financials
from finance_plugin.research_financials_sec import parse_facts
from finance_plugin.research_report import compile_research_report
from finance_plugin.runtime_market_data import parse_fundamentals_lookup_arguments

from tests import test_research_monitor as support
from tests.test_research_financials import company, row
from tests.test_research_monitor import begin, call

runtime = support.runtime


def test_revised_financials_merge_and_monitor_preserve_current_eligibility(runtime):
    snapshot = begin(runtime)
    frozen = datetime.fromisoformat(snapshot["cutoffAt"])

    class Provider:
        def fetch(self, *args, **kwargs):
            data = company(
                {
                    "Revenues": {
                        "USD": [
                            row(100),
                            row(110, filed="2025-08-10", acc="0000000001-25-000002"),
                            row(120, filed="2025-09-10", acc="0000000001-25-000003"),
                        ]
                    }
                }
            )
            facts, gaps = parse_facts(data, {}, frozen)
            return "0000789019", frozen, frozen, facts, {}, gaps

    financials = lookup_financials(
        Provider(), parse_fundamentals_lookup_arguments('{"symbol":"MSFT","statementLimit":1}')
    )
    coverage = {item["sourceId"]: item for item in financials["coverage"]}
    assert coverage["sec"]["complete"] and len(coverage["sec"]["evidenceIds"]) == 1
    assert not coverage["sec_history"]["complete"]
    assert len(coverage["sec_history"]["evidenceIds"]) == 2
    merged = merge_evidence(
        ResearchMergeInput.model_validate(
            {
                "symbol": "MSFT",
                "asOfDate": snapshot["asOfDate"],
                "cutoffAt": snapshot["cutoffAt"],
                "groups": [financials["evidence"]],
                "coverageGroups": [financials["coverage"]],
            }
        )
    )
    assert len(merged.evidence) == 3
    observed = call(
        runtime,
        "monitor_observe",
        {
            "snapshotId": snapshot["snapshotId"],
            "evidence": [item.model_dump(mode="json", by_alias=True) for item in merged.evidence],
            "coverage": [item.model_dump(mode="json", by_alias=True) for item in merged.coverage],
        },
    )
    assert observed["state"] == "no_baseline"
    old = next(item for item in merged.evidence if item.value == "100")
    report = compile_research_report(
        {
            "symbol": "MSFT",
            "asOfDate": snapshot["asOfDate"],
            "cutoffAt": snapshot["cutoffAt"],
            "evidence": [item.model_dump(mode="json", by_alias=True) for item in merged.evidence],
            "claims": [
                {
                    "claimId": "old-revenue",
                    "metric": "revenue",
                    "formula": "identity",
                    "evidenceIds": [old.evidence_id],
                    "value": "100",
                    "unit": "USD",
                    "periodStart": "2024-07-01",
                    "periodEnd": "2025-06-30",
                }
            ],
        }
    )
    assert report["status"] == "insufficient_evidence"
    assert any("old-revenue" in gap for gap in report["dataGaps"])
    assert len(report["evidence"]) == 3

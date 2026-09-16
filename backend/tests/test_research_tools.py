"""Canonical research reports bind immutable observations through the public plugin."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

for directory in ("runtime", "finance"):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / directory))

from finance_plugin.main import create_app  # noqa: E402
from finance_plugin.providers.quote_provider import DeterministicQuoteProvider  # noqa: E402


def identity(run_id=None, operation_id=None):
    return {
        "runId": run_id or str(uuid4()),
        "nodeId": "save",
        "invocationId": str(uuid4()),
        "operationId": operation_id or str(uuid4()),
        "resourceBindings": {"finance-market-data": {"allowedSymbols": ["MSFT"]}},
        "resourceGrants": ["finance-market-data"],
    }


def test_canonical_report_saved_downloaded_and_journaled_without_body_changes(database_url):
    app = create_app(database_url, DeterministicQuoteProvider())
    now = datetime.now(UTC)
    evidence = {
        "evidenceId": "revenue-1",
        "sourceId": "sec:filing-1",
        "kind": "fact",
        "title": "Reported revenue",
        "sourceType": "sec",
        "symbol": "MSFT",
        "metric": "revenue",
        "value": "123.45",
        "unit": "USD",
        "currency": "USD",
        "periodEnd": "2026-06-30",
        "publishedAt": (now - timedelta(days=1)).isoformat(),
        "retrievedAt": now.isoformat(),
        "url": "https://www.sec.gov/Archives/filing-1.htm",
        "locator": "Statement of income, revenue",
        "verified": True,
    }
    with TestClient(app) as client:
        compiled = app.state.execute(
            "signaldeck/finance/research_report_compile",
            {
                "symbol": "MSFT",
                "asOfDate": now.date().isoformat(),
                "evidence": [evidence],
                "claims": [
                    {
                        "claimId": "revenue",
                        "metric": "revenue",
                        "evidenceIds": ["revenue-1"],
                        "value": "123.45",
                        "unit": "USD",
                        "periodEnd": "2026-06-30",
                    }
                ],
            },
            identity(),
        )
        assert compiled["status"] == "validated"
        context = identity()
        arguments = {key: compiled[key] for key in ("name", "content")}
        saved = app.state.execute("signaldeck/finance/research_reports_create", arguments, context)
        assert (
            app.state.execute("signaldeck/finance/research_reports_create", arguments, context)
            == saved
        )
        assert saved["content"] == compiled["content"]
        assert evidence["url"] in saved["content"]
        response = client.get(f"/api/reports/{saved['slug']}/download")
        assert response.status_code == 200 and response.text == compiled["content"]
        assert "researchSnapshotId" not in saved["metadata"]
        assert (
            app.state.journal.query(
                context["operationId"],
                context["resourceBindings"],
                ["signaldeck/finance/research_reports_create"],
            )["output"]
            == saved
        )
        assert (
            client.patch(f"/api/reports/{saved['slug']}", json={"content": "changed"}).status_code
            == 409
        )


def test_monitor_report_requires_exact_run_snapshot_and_exposes_read_only_binding(database_url):
    app = create_app(database_url, DeterministicQuoteProvider())
    run_id = str(uuid4())
    with TestClient(app) as client:

        def call(name, arguments, run=run_id):
            return app.state.execute("signaldeck/finance/" + name, arguments, identity(run))

        snapshot = call(
            "monitor_begin",
            {
                "monitorKey": "cash-review",
                "scope": {
                    "symbol": "MSFT",
                    "cik": "0000789019",
                    "question": "Cash",
                    "horizonMonths": 3,
                    "ruleVersion": "1",
                    "sources": [{"sourceId": "sec", "maxAgeSeconds": 3600}],
                },
            },
        )
        cutoff = datetime.fromisoformat(snapshot["cutoffAt"])
        call(
            "monitor_observe",
            {
                "snapshotId": snapshot["snapshotId"],
                "evidence": [
                    {
                        "evidenceId": "cash",
                        "sourceId": "sec:filing",
                        "kind": "fact",
                        "title": "Cash",
                        "metric": "cash",
                        "value": "100",
                        "unit": "USD",
                        "symbol": "MSFT",
                        "publishedAt": (cutoff - timedelta(days=1)).isoformat(),
                        "retrievedAt": cutoff.isoformat(),
                        "verified": True,
                        "sourceType": "sec",
                    }
                ],
                "coverage": [
                    {
                        "sourceId": "sec",
                        "complete": True,
                        "observedAt": cutoff.isoformat(),
                        "evidenceIds": ["cash"],
                    }
                ],
            },
        )
        args = {
            "name": "Snapshot report",
            "content": "Canonical body",
            "snapshotId": snapshot["snapshotId"],
        }
        with pytest.raises(ValueError, match="run_mismatch"):
            call("research_reports_create", args, run=str(uuid4()))
        saved = call("research_reports_create", args)
        assert saved["metadata"]["researchSnapshotId"] == snapshot["snapshotId"]
        attached = call(
            "monitor_report_attach",
            {
                "snapshotId": snapshot["snapshotId"],
                "status": "succeeded",
                "reportId": saved["id"],
            },
        )
        assert attached["reportId"] == saved["id"] and attached["reportDigest"].startswith(
            "sha256:"
        )
        assert (
            client.post(
                "/api/reports",
                json={
                    "name": "Spoof",
                    "content": "body",
                    "metadata": {"researchSnapshotId": snapshot["snapshotId"]},
                },
            ).status_code
            == 422
        )


def test_market_evidence_cannot_bypass_symbol_grants(database_url):
    app = create_app(database_url, DeterministicQuoteProvider())
    with pytest.raises(ValueError, match="symbol_not_granted"):
        app.state.execute(
            "signaldeck/finance/research_market_evidence",
            {"symbol": "NVDA", "asOfDate": "2026-03-08"},
            identity(),
        )
    frozen = app.state.execute(
        "signaldeck/finance/research_scope_freeze",
        {"symbol": "MSFT", "asOfDate": "2026-03-08"},
        identity(),
    )
    assert frozen["cutoffAt"] == "2026-03-09T04:00:00Z"
    with pytest.raises(ValueError, match="future"):
        app.state.execute(
            "signaldeck/finance/research_scope_freeze",
            {"symbol": "MSFT", "asOfDate": "2099-01-01"},
            identity(),
        )

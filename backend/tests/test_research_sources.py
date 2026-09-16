"""Original-document and exact prediction source contracts at the HTTP boundary."""

import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "digital_oracle", "finance"):
    sys.path.insert(0, str(PLUGINS / directory))

from oracle_plugin.research_documents import (  # noqa: E402
    DocumentQuery,
    DocumentsResult,
    cutoff,
    lookup_documents,
)
from oracle_plugin.research_prediction import (  # noqa: E402
    PredictionQuery,
    PredictionResult,
    lookup_prediction,
)
from plugin_runtime.serialization import model_wire_schema  # noqa: E402


@pytest.fixture
def source_http(monkeypatch):
    original = httpx.Client

    def install(handler):
        monkeypatch.setattr(
            httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
        )

    return install


def test_original_excerpt_provenance_cutoff_and_schema(source_http):
    body = (
        '<html><meta property="article:published_time" content="2026-01-01T12:00:00Z">'
        "<script>hidden</script><p>Gross margin 74% plus or minus 50 basis points.</p></html>"
    )
    source_http(lambda r: httpx.Response(200, text=body, headers={"content-type": "text/html"}))
    result = lookup_documents(
        {"urls": ["https://investor.example.com/release"], "asOfDate": "2026-01-02"}
    )
    document = result.documents[0]
    assert document.status == "read"
    assert "hidden" not in document.text
    assert document.document_digest.startswith("sha256:")
    assert not result.evidence[0].verified
    assert "source_authority_not_independently_confirmed" in document.gaps
    assert result.evidence[0].source_type is None
    assert result.evidence[0].url == document.url
    Draft202012Validator(model_wire_schema(DocumentsResult)).validate(
        result.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    after = lookup_documents({"urls": [document.url], "asOfDate": "2025-12-31"})
    assert after.documents[0].status == "after_cutoff"
    assert not after.evidence
    assert after.documents[0].text is None


@pytest.mark.parametrize(
    "kind,body,status",
    [
        ("application/pdf", b"%PDF scanned", "unavailable"),
        ("text/html", b"<p>Undated news</p>", "publication_unknown"),
        ("text/plain", b"", "unavailable"),
    ],
)
def test_unsupported_and_undated_sources_not_verified(source_http, kind, body, status):
    source_http(lambda r: httpx.Response(200, content=body, headers={"content-type": kind}))
    result = lookup_documents({"urls": ["https://example.com/policy"], "asOfDate": "2026-01-01"})
    assert result.documents[0].status == status
    assert not result.coverage[0].complete
    assert all(not e.verified for e in result.evidence)


def test_limits_and_failures_are_bounded_and_do_not_echo_credentials(source_http, monkeypatch):
    monkeypatch.setenv("EDGAR_CONTACT_EMAIL", "private-contact@example.com")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, text="private-contact@example.com")

    source_http(handler)
    result = lookup_documents(
        {
            "urls": [
                "https://www.sec.gov/Archives/x",
                "https://www.sec.gov/Archives/x",
                "https://127.0.0.1/a",
            ]
        }
    )
    assert len(calls) == 1
    assert "private-contact" not in result.model_dump_json()
    assert len(result.documents) == 2


def test_documents_size_and_redirect_are_not_success(source_http):
    source_http(
        lambda r: httpx.Response(
            200, content=b"a" * 8_000_001, headers={"content-type": "text/plain"}
        )
    )
    assert (
        lookup_documents({"urls": ["https://example.com/a"]}).documents[0].status == "unavailable"
    )
    source_http(lambda r: httpx.Response(302, headers={"location": "https://example.com/b"}))
    assert (
        lookup_documents({"urls": ["https://example.com/a"]}).documents[0].status == "unavailable"
    )


def test_cutoff_new_york_dst_and_future_clamp():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    assert cutoff(DocumentQuery(as_of_date="2026-03-08"), now) == datetime(
        2026, 3, 9, 4, tzinfo=UTC
    )
    assert cutoff(DocumentQuery(as_of_date="2026-01-01"), now) == datetime(
        2026, 1, 2, 5, tzinfo=UTC
    )
    assert cutoff(DocumentQuery(as_of_date="2027-01-01"), now) == now


def test_sec_automatic_original_uses_accepted_time(source_http, monkeypatch):
    monkeypatch.setenv("EDGAR_CONTACT_EMAIL", "test@example.com")
    from oracle_plugin import research_documents_discovery

    url = "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/report.htm"
    monkeypatch.setattr(
        research_documents_discovery,
        "filing_sources",
        lambda *a: {"filings": [{"url": url, "acceptedAt": "2026-01-01T10:00:00Z"}]},
    )
    source_http(
        lambda r: httpx.Response(
            200, text="<p>Original filing</p>", headers={"content-type": "text/html"}
        )
    )
    result = lookup_documents({"symbol": "NVDA", "asOfDate": "2026-01-02"})
    assert result.evidence[0].source_id == "sec:0001045810-26-000010"
    assert result.evidence[0].verified


def selection(venue="polymarket"):
    return {
        "venue": venue,
        "contractId": "17",
        "hypothesis": "Policy exposure",
        "reason": "Explicit selected event",
    }


def polymarket_handler(rules="Official rule"):
    def handler(request):
        if request.url.host == "gamma-api.polymarket.com":
            assert request.url.path == "/markets/17"
            return httpx.Response(
                200,
                json={
                    "id": "17",
                    "events": [{"id": "3"}],
                    "description": rules,
                    "resolutionSource": "https://official.example.com/rule",
                    "outcomes": '["Yes", "No"]',
                    "clobTokenIds": '["101", "102"]',
                    "endDate": "2027-01-01T00:00:00Z",
                    "volume": "12000.01",
                    "liquidity": "5000",
                },
            )
        return httpx.Response(
            200,
            json={
                "asset_id": request.url.params["token_id"],
                "timestamp": "1767268800000",
                "bids": [{"price": "0.42"}, {"price": "0.44"}],
                "asks": [{"price": "0.46"}],
            },
        )

    return handler


def test_explicit_prediction_identity_rules_quote_and_schema(source_http):
    source_http(polymarket_handler())
    result = lookup_prediction({"events": [selection()]})
    assert len(result.snapshots) == 2
    assert result.snapshots[0].bid == "0.44"
    assert result.snapshots[0].token_id == "101"
    assert result.evidence[0].verified
    assert result.coverage[0].complete
    Draft202012Validator(model_wire_schema(PredictionResult)).validate(
        result.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    old = result.snapshots[0].rule_version
    source_http(polymarket_handler("Changed settlement rule"))
    assert lookup_prediction({"events": [selection()]}).snapshots[0].rule_version != old


def test_prediction_cutoff_does_not_return_future_prices(source_http):
    source_http(polymarket_handler())
    result = lookup_prediction({"events": [selection()], "asOfDate": "2025-12-01"})
    assert all(s.bid is None and s.volume is None for s in result.snapshots)
    assert all(e.value is None and not e.verified for e in result.evidence)
    assert not result.coverage[0].complete


def test_wrong_prediction_id_and_outage_degrade(source_http):
    source_http(lambda r: httpx.Response(200, json={"id": "18"}))
    assert not lookup_prediction({"events": [selection()]}).snapshots
    source_http(lambda r: httpx.Response(503))
    result = lookup_prediction({"events": [selection()]})
    assert result.gaps == ["polymarket:selected_event_unavailable"]


def test_kalshi_metadata_time_is_not_quote_time(source_http):
    source_http(
        lambda r: httpx.Response(
            200,
            json={
                "market": {
                    "ticker": "17",
                    "event_ticker": "KX17",
                    "rules_primary": "Settlement rule",
                    "updated_time": "2026-01-01T00:00:00Z",
                    "yes_bid_dollars": "0.42",
                    "yes_ask_dollars": "0.45",
                    "volume_fp": "100.25",
                    "status": "active",
                }
            },
        )
    )
    current = lookup_prediction({"events": [selection("kalshi")]})
    assert current.snapshots[0].bid == "0.42"
    assert current.snapshots[0].quoted_at is None
    assert not current.evidence[0].verified
    historical = lookup_prediction({"events": [selection("kalshi")], "asOfDate": "2026-01-01"})
    assert historical.snapshots[0].bid is None
    assert all(e.value is None and not e.verified for e in historical.evidence)


def test_inputs_closed_and_bounded():
    with pytest.raises(ValueError):
        PredictionQuery.model_validate({"events": [selection()] * 4})
    with pytest.raises(ValueError):
        DocumentQuery.model_validate({"urls": ["https://example.com"] * 6})
    with pytest.raises(ValueError):
        PredictionQuery.model_validate(
            {"events": [{"venue": "kalshi", "hypothesis": "x", "reason": "y"}]}
        )


def test_evidence_public_contract_matches_finance():
    from finance_plugin.research_evidence import ResearchEvidence as FinanceEvidence
    from oracle_plugin.research_documents_evidence import ResearchEvidence

    assert model_wire_schema(ResearchEvidence) == model_wire_schema(FinanceEvidence)


def test_sec_form4_evidence_and_no_transactions(monkeypatch, source_http):
    from oracle_plugin import research_documents_insider

    filing = {
        "accessionNumber": "0001045810-26-000010",
        "acceptedAt": "2026-01-01T12:00:00Z",
        "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/xslF345X05/a.xml",
    }
    transaction = {
        "accessionNumber": filing["accessionNumber"],
        "shares": "100.05",
        "price": "170.10",
        "transactionDate": "2025-12-31",
        "acquiredDisposedCode": "A",
    }
    monkeypatch.setattr(
        research_documents_insider,
        "filing_sources",
        lambda *a, **kw: {"filings": [filing], "ownershipTransactions": [transaction]},
    )
    source_http(
        lambda r: httpx.Response(200, text="<p>Undated</p>", headers={"content-type": "text/html"})
    )
    result = lookup_documents(
        {
            "urls": ["https://example.com/report"],
            "symbol": "NVDA",
            "includeInsider": True,
            "asOfDate": "2026-01-01",
        }
    )
    insider = next(e for e in result.evidence if e.metric == "insider_transaction_shares")
    assert insider.value == "100.05"
    assert insider.source_id == "sec:" + filing["accessionNumber"]
    assert insider.verified
    assert insider.evidence_id not in result.coverage[1].evidence_ids
    monkeypatch.setattr(
        research_documents_insider,
        "filing_sources",
        lambda *a, **kw: {"filings": [filing], "ownershipTransactions": []},
    )
    empty = lookup_documents(
        {"urls": ["https://example.com/report"], "symbol": "NVDA", "includeInsider": True}
    )
    assert not any(e.metric == "insider_transaction_shares" for e in empty.evidence)


def test_polymarket_event_selection_is_exact_and_bounded(source_http):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/events/22":
            return httpx.Response(
                200,
                json={
                    "id": "22",
                    "markets": [
                        {
                            "id": str(i),
                            "description": "Rule",
                            "resolutionSource": "Official",
                            "outcomes": '["Yes", "No"]',
                            "clobTokenIds": '["101", "102"]',
                        }
                        for i in range(20)
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "asset_id": request.url.params["token_id"],
                "timestamp": "1767268800000",
                "bids": [],
                "asks": [],
            },
        )

    source_http(handler)
    selected = selection()
    del selected["contractId"]
    selected["eventId"] = "22"
    result = lookup_prediction({"events": [selected]})
    assert len(calls) == 7
    assert len(result.snapshots) == 6
    assert "truncated" in result.gaps[0]
    assert not result.coverage[0].complete


def test_token_identity_mismatch_never_emits_a_quote(source_http):
    delegate = polymarket_handler()

    def handler(request):
        if request.url.host == "clob.polymarket.com":
            return httpx.Response(
                200,
                json={
                    "asset_id": "unrelated",
                    "timestamp": "1767268800000",
                    "bids": [{"price": "0.50"}],
                },
            )
        return delegate(request)

    source_http(handler)
    result = lookup_prediction({"events": [selection()]})
    assert all(e.value is None and not e.verified for e in result.evidence)
    assert all("orderbook_unavailable" in s.gaps for s in result.snapshots)


def test_prediction_empty_selection_never_fetches(source_http):
    def forbidden(request):
        raise AssertionError("empty selection must not fetch")

    source_http(forbidden)
    result = lookup_prediction({"events": []})
    assert result.gaps == ["prediction_selection_empty"]
    assert not result.coverage[0].complete


def test_prediction_metadata_survives_quote_absence_and_rule_change(source_http):
    source_http(polymarket_handler())
    first = lookup_prediction({"events": [selection()]})
    source_http(polymarket_handler("Amended settlement rule"))
    second = lookup_prediction({"events": [selection()]})
    assert first.evidence[0].prediction.rule_version != second.evidence[0].prediction.rule_version
    assert first.evidence[0].metric != second.evidence[0].metric
    historical = lookup_prediction({"events": [selection()], "asOfDate": "2025-01-01"})
    metadata = historical.evidence[0]
    assert metadata.prediction.contract_id == "17"
    assert metadata.prediction.deadline is not None
    assert metadata.value is None
    assert metadata.published_at is None
    assert not metadata.verified


def test_html_removes_inline_xbrl_and_preserves_table_cells():
    from oracle_plugin.research_documents_extract import OriginalHTML

    parser = OriginalHTML()
    parser.feed(
        "<html><head><title>Title</title></head><body><ix:header>"
        "<ix:hidden>0001045810us-gaap:Cash</ix:hidden></ix:header>"
        '<div style="display:none">secret xbrl</div><h2>Results of Operations</h2>'
        "<table><tr><td>Revenue</td><td>100</td><td>80</td></tr></table></body></html>"
    )
    body = parser.body()
    assert "0001045810" not in body and "secret xbrl" not in body
    assert "Revenue | 100 | 80" in body
    assert "Results of Operations" in body


def test_long_document_passages_target_substantive_sections_with_positions():
    from oracle_plugin.research_documents_extract import select_passages

    body = "Management Discussion | 42\n" + "Cover and contents\n" * 2500
    body += "Management Discussion and Analysis\n" + "Revenue increased due to demand.\n" * 200
    body += "Outlook and Guidance\nGross margin is 74% plus or minus 50 basis points.\n"
    passages = select_passages(body)
    assert any("Gross margin is 74%" in passage.text for passage in passages)
    assert any(p.title == "Management discussion" for p in passages)
    assert all("paragraph " in p.locator for p in passages)
    assert all("Cover and contents" not in p.text for p in passages)
    assert len(passages) <= 5


def test_document_and_insider_failures_reach_top_level_gaps(source_http, monkeypatch):
    from oracle_plugin import research_documents_insider
    from oracle_plugin.research_documents import SourceCoverage

    monkeypatch.setattr(
        research_documents_insider,
        "insider_evidence",
        lambda *args: (
            [],
            SourceCoverage(
                source_id="insider",
                complete=False,
                observed_at=datetime.now(UTC),
                warning="form4_source_unavailable",
            ),
        ),
    )
    source_http(lambda r: httpx.Response(403))
    result = lookup_documents(
        {"urls": ["https://example.com/file?private=do-not-echo"], "includeInsider": True}
    )
    assert any("https://example.com/file: document_unavailable" == gap for gap in result.gaps)
    assert not any("do-not-echo" in gap for gap in result.gaps)
    assert "insider: form4_source_unavailable" in result.gaps
    assert not result.coverage[-1].complete
    empty = lookup_documents({})
    assert "no_documents_selected_or_available" in empty.gaps


def test_partial_sec_passages_do_not_claim_complete_coverage(source_http, monkeypatch):
    from oracle_plugin import research_documents_discovery

    url = "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/report.htm"
    monkeypatch.setenv("EDGAR_CONTACT_EMAIL", "test@example.com")
    monkeypatch.setattr(
        research_documents_discovery,
        "filing_sources",
        lambda *a: {"filings": [{"url": url, "acceptedAt": "2026-01-01T10:00:00Z"}]},
    )
    html = (
        "<p>Cover</p>" * 7000 + "<h2>Results of Operations</h2><p>Revenue increased.</p>"
        "<h2>Outlook</h2><p>Gross margin guidance is 74%.</p>"
    )
    source_http(lambda r: httpx.Response(200, text=html, headers={"content-type": "text/html"}))
    result = lookup_documents({"symbol": "NVDA"})
    assert result.documents[0].status == "read"
    assert not result.coverage[0].complete
    assert any("selected_passages_only" in gap for gap in result.gaps)
    assert any("Gross margin guidance" in evidence.text for evidence in result.evidence)
    assert result.evidence[0].verified


@pytest.mark.parametrize("cik,accepted", [("0000789019", True), ("0001045810", False)])
def test_explicit_symbol_and_cik_must_identify_the_same_document_issuer(monkeypatch, cik, accepted):
    from oracle_plugin.research_documents_discovery import filing_sources

    def resolved(context, arguments):
        assert arguments["ticker"] == "MSFT"
        assert arguments["cik"] is None
        return {"cik": "0000789019", "filings": [{"url": "https://www.sec.gov/msft.htm"}]}

    monkeypatch.setattr(
        "oracle_plugin.research_documents_discovery.execute_sec_filings_lookup", resolved
    )
    result = filing_sources("MSFT", cik, None)
    assert bool(result["filings"]) is accepted
    if not accepted:
        assert result["ownershipTransactions"] == []
        assert result["warnings"] == [{"code": "sec_symbol_cik_mismatch"}]

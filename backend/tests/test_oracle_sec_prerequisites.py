"""Form 4 summaries require raw XML and actual supported transaction records."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "digital_oracle"):
    sys.path.insert(0, str(PLUGINS / directory))

from oracle_plugin.config import reset_digital_oracle_settings_cache  # noqa: E402
from oracle_plugin.contracts import RuntimeToolContext  # noqa: E402
from oracle_plugin.runtime_sec_filings import (  # noqa: E402
    execute_sec_filings_lookup,
    parse_sec_filings_lookup_arguments,
)

_CONTACT = "sec-fixture@example.invalid"
_ARCHIVE = "/Archives/edgar/data/1045810/000104581026000020"
_TRANSACTION = """
<nonDerivativeTransaction>
  <transactionDate><value>2026-02-20</value></transactionDate>
  <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
  <transactionAmounts>
    <transactionShares><value>10</value></transactionShares>
    <transactionPricePerShare><value>120.25</value></transactionPricePerShare>
    <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
  </transactionAmounts>
</nonDerivativeTransaction>
"""


@pytest.fixture
def mock_edgar(monkeypatch: pytest.MonkeyPatch):
    client_class = httpx.Client

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        monkeypatch.setattr(
            "oracle_plugin.runtime_sec_filings.httpx.Client",
            lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
        )

    reset_digital_oracle_settings_cache()
    yield install
    reset_digital_oracle_settings_cache()


def _lookup(mock_edgar, primary_document: str, body: str, *, form: str = "4"):
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        requests.append(path)
        assert _CONTACT in request.headers["User-Agent"]
        if path == "/files/company_tickers.json":
            return httpx.Response(
                200,
                json={"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}},
            )
        if path == "/submissions/CIK0001045810.json":
            return httpx.Response(
                200,
                json={
                    "name": "NVIDIA CORP",
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0001045810-26-000020"],
                            "form": [form],
                            "filingDate": ["2026-02-22"],
                            "primaryDocument": [primary_document],
                        }
                    },
                },
            )
        if path == f"{_ARCHIVE}/form4.xml":
            return httpx.Response(200, text=body, headers={"Content-Type": "application/xml"})
        if "/xsl" in path:
            return httpx.Response(200, text="<html><body>Rendered ownership report</body></html>")
        raise AssertionError(f"Unexpected SEC request: {path}")

    mock_edgar(respond)
    payload = execute_sec_filings_lookup(
        RuntimeToolContext(secrets={"edgar_contact_email": _CONTACT}),
        parse_sec_filings_lookup_arguments(
            json.dumps({"ticker": "NVDA", "includeOwnershipTransactions": True})
        ),
    )
    assert _CONTACT not in json.dumps(payload)
    return payload, requests


@pytest.mark.parametrize("primary_document", ["form4.xml", "xslF345X05/form4.xml"])
@pytest.mark.parametrize("form", ["4", "4/A"])
def test_form4_reads_raw_xml_and_preserves_the_filing_link(mock_edgar, primary_document, form):
    payload, requests = _lookup(
        mock_edgar,
        primary_document,
        '<ownershipDocument xmlns="urn:sec:ownership">'
        "<issuer><issuerName>NVIDIA CORP</issuerName></issuer>"
        f"<nonDerivativeTable>{_TRANSACTION}</nonDerivativeTable></ownershipDocument>",
        form=form,
    )

    assert requests[-1] == f"{_ARCHIVE}/form4.xml"
    assert len(requests) == 3
    assert payload["filings"][0]["url"] == f"https://www.sec.gov{_ARCHIVE}/{primary_document}"
    assert len(payload["ownershipTransactions"]) == 1
    transaction = payload["ownershipTransactions"][0]
    assert transaction["issuerName"] == "NVIDIA CORP"
    assert transaction["transactionCode"] == "P"
    assert transaction["shares"] == "10"
    assert transaction["price"] == "120.25"
    assert payload["warnings"] == []


@pytest.mark.parametrize(
    "body",
    [
        "<derivativeTable><derivativeTransaction/></derivativeTable>",
        "<nonDerivativeTable><nonDerivativeHolding/></nonDerivativeTable>",
        "",
    ],
)
def test_form4_without_supported_transactions_returns_empty_with_warning(mock_edgar, body):
    payload, _ = _lookup(mock_edgar, "form4.xml", f"<ownershipDocument>{body}</ownershipDocument>")

    assert payload["ownershipTransactions"] == []
    warnings = payload["warnings"]
    assert any(
        warning["code"] == "sec_filings_ownership_unavailable"
        and "non-derivative" in warning["message"]
        for warning in warnings
    )


def test_mixed_form4_discloses_excluded_derivative_transactions(mock_edgar):
    payload, _ = _lookup(
        mock_edgar,
        "xslF345X05/form4.xml",
        f"<ownershipDocument><nonDerivativeTable>{_TRANSACTION}</nonDerivativeTable>"
        "<derivativeTable><derivativeTransaction/></derivativeTable></ownershipDocument>",
    )

    assert len(payload["ownershipTransactions"]) == 1
    warning = next(
        warning
        for warning in payload["warnings"]
        if warning["code"] == "sec_filings_ownership_partial"
    )
    assert "derivative transactions are not included" in warning["message"]
    assert {"key": "accessionNumber", "value": "0001045810-26-000020"} in warning["details"]

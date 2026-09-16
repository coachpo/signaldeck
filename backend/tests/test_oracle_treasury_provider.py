"""Treasury debt-category average rates retain their identity and observation window."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "digital_oracle"):
    sys.path.insert(0, str(PLUGINS / directory))

from oracle_plugin.config import reset_digital_oracle_settings_cache  # noqa: E402
from oracle_plugin.contracts import RuntimeToolContext  # noqa: E402
from oracle_plugin.runtime_macro_rates import (  # noqa: E402
    execute_macro_rates_lookup,
    parse_macro_rates_lookup_arguments,
)

_TREASURY_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
    "v2/accounting/od/avg_interest_rates"
)


@pytest.fixture
def mock_treasury(monkeypatch: pytest.MonkeyPatch):
    client_class = httpx.Client

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        monkeypatch.setattr(
            "oracle_plugin.runtime_macro_rates_client.httpx.Client",
            lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
        )

    reset_digital_oracle_settings_cache()
    yield install
    reset_digital_oracle_settings_cache()


def _lookup(**arguments: object) -> dict[str, object]:
    return execute_macro_rates_lookup(
        RuntimeToolContext(),
        parse_macro_rates_lookup_arguments(json.dumps({"sources": ["treasury"], **arguments})),
    )


def _row(record_date: str, security: str = "Treasury Bills", **values: object) -> dict[str, object]:
    return {
        "record_date": record_date,
        "security_type_desc": "Marketable",
        "security_desc": security,
        "avg_interest_rate_amt": "3.788",
        **values,
    }


def test_treasury_returns_average_rates_with_distinct_security_identities(
    mock_treasury,
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    _row("2026-07-31"),
                    _row("2026-08-31", "Treasury Notes"),
                    _row("2026-08-31"),
                    _row("2026-08-31", security_type_desc="Non-marketable"),
                ]
            },
        )

    mock_treasury(respond)
    payload = _lookup(families=["macro_indicators"], itemLimit=4)
    series = payload["series"]
    assert [row["date"] for row in series] == ["2026-08-31"] * 3 + ["2026-07-31"]
    assert len({row["seriesId"] for row in series}) == 3
    bills = [
        row
        for row in series
        if row["label"] == "Average interest rate: Marketable / Treasury Bills"
    ]
    assert len({row["seriesId"] for row in bills}) == 1
    assert len(bills) == 2
    assert all(row["family"] == "macro_indicators" for row in series)
    assert all(row["tenor"] is None for row in series)
    assert all(row["sourceUrl"] == _TREASURY_URL for row in series)
    assert all(row["unit"] == "percent" and row["value"] == "3.788" for row in series)
    assert requests[0].url.params["sort"] == "-record_date"
    assert requests[0].url.params["page[size]"] == "4"
    assert "filter" not in requests[0].url.params
    assert payload["warnings"] == []
    selected = _lookup(seriesIds=[bills[0]["seriesId"].upper()], itemLimit=4)
    assert selected["series"] == bills
    assert selected["warnings"] == []


def test_treasury_filters_observation_window_and_discloses_missing_vintage(
    mock_treasury,
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        # Deliberately include rows outside the requested window to check local enforcement.
        return httpx.Response(
            200,
            json={"data": [_row(value) for value in ("2025-12-31", "2026-02-28", "2026-03-31")]},
        )

    mock_treasury(respond)
    payload = _lookup(startDate="2026-01-01", endDate="2026-12-31", asOfDate="2026-03-15")
    assert [row["date"] for row in payload["series"]] == ["2026-02-28"]
    assert requests[0].url.params["filter"] == (
        "record_date:gte:2026-01-01,record_date:lte:2026-03-15"
    )
    assert [warning["code"] for warning in payload["warnings"]] == [
        "macro_rates_vintage_unavailable"
    ]
    assert "publication times and revisions are unavailable" in payload["warnings"][0]["message"]


def test_treasury_end_date_is_preserved_without_as_of_date(mock_treasury) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.params["filter"] == "record_date:lte:2026-01-31"
        return httpx.Response(200, json={"data": [_row("2026-01-31"), _row("2026-02-28")]})

    mock_treasury(respond)
    payload = _lookup(endDate="2026-01-31")
    assert [row["date"] for row in payload["series"]] == ["2026-01-31"]
    assert payload["warnings"] == []


@pytest.mark.parametrize(
    "arguments",
    [
        {"families": ["yield_curve"]},
        {"startDate": "2026-03-01", "asOfDate": "2026-02-01"},
    ],
)
def test_treasury_does_not_fetch_an_inapplicable_family_or_empty_window(
    mock_treasury, arguments
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise AssertionError("An inapplicable Treasury query must not fetch provider data")

    mock_treasury(respond)
    payload = _lookup(**arguments)
    assert payload["series"] == []
    assert "macro_rates_empty" in {warning["code"] for warning in payload["warnings"]}


def test_treasury_does_not_invent_a_security_identity_for_malformed_rows(
    mock_treasury,
) -> None:
    mock_treasury(
        lambda request: httpx.Response(
            200,
            json={
                "data": [
                    _row("2026-08-31", security_type_desc=None),
                    _row("2026-08-31", security_desc=""),
                    _row("2026-08-31", avg_interest_rate_amt="unavailable"),
                ]
            },
        )
    )
    payload = _lookup()
    assert payload["series"] == []
    assert (
        sum(warning["code"] == "macro_rates_malformed_payload" for warning in payload["warnings"])
        == 3
    )


def _series_id(security: str, security_type: str = "Marketable") -> str:
    return f"UST-AVG-INTEREST:{quote(security_type, safe='')}:{quote(security, safe='')}"


def test_treasury_selects_requested_series_before_applying_item_limit(mock_treasury) -> None:
    requests: list[httpx.Request] = []
    available = [_row("2026-08-31"), _row("2026-08-31", "Treasury Notes")]

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        size = int(request.url.params["page[size]"])
        page = int(request.url.params.get("page[number]", "1"))
        return httpx.Response(200, json={"data": available[(page - 1) * size : page * size]})

    mock_treasury(respond)
    payload = _lookup(seriesIds=[_series_id("Treasury Notes").upper()], itemLimit=1)
    assert [row["seriesId"] for row in payload["series"]] == [_series_id("Treasury Notes")]
    assert len(requests) == 1
    assert payload["warnings"] == []


def test_treasury_paginates_and_matches_multiple_casefolded_encoded_identities(mock_treasury):
    requests: list[httpx.Request] = []
    selected = ["Treasury Notes", "Notes: inflation / indexed"]
    available = [
        *[_row("2026-08-31", f"Other category {index}") for index in range(100)],
        *[_row("2026-08-31", security) for security in selected],
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        size = int(request.url.params["page[size]"])
        page = int(request.url.params["page[number]"])
        assert request.url.params["filter"] == "record_date:gte:2026-08-01"
        return httpx.Response(200, json={"data": available[(page - 1) * size : page * size]})

    mock_treasury(respond)
    payload = _lookup(
        seriesIds=["FEDFUNDS", *[_series_id(security).lower() for security in selected]],
        startDate="2026-08-01",
        itemLimit=2,
    )
    assert {row["seriesId"] for row in payload["series"]} == {
        _series_id(security) for security in selected
    }
    assert [request.url.params["page[number]"] for request in requests] == ["1", "2"]
    assert payload["warnings"] == []


@pytest.mark.parametrize(
    "series_id",
    [
        "FEDFUNDS",
        "UST-10Y",
        "UST-AVG-INTEREST",
        "UST-AVG-INTEREST:Marketable:",
        "UST-AVG-INTEREST:Marketable:Treasury%ZZNotes",
        "UST-AVG-INTEREST:Marketable:Treasury%FFNotes",
        "UST-AVG-INTEREST:Marketable:Treasury%2Notes",
    ],
)
def test_treasury_unrelated_or_malformed_series_ids_do_not_fetch(mock_treasury, series_id):
    def respond(request: httpx.Request) -> httpx.Response:
        raise AssertionError("An unrelated or malformed series ID must not fetch Treasury data")

    mock_treasury(respond)
    payload = _lookup(seriesIds=[series_id], itemLimit=1)
    assert payload["series"] == []
    assert "macro_rates_empty" in {warning["code"] for warning in payload["warnings"]}


def test_treasury_discloses_when_requested_series_exceeds_bounded_search(mock_treasury):
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        size = int(request.url.params["page[size]"])
        return httpx.Response(200, json={"data": [_row("2026-08-31")] * size})

    mock_treasury(respond)
    payload = _lookup(seriesIds=[_series_id("Treasury Notes")], itemLimit=1)
    assert payload["series"] == []
    assert len(requests) == 10
    assert "macro_rates_treasury_search_truncated" in {
        warning["code"] for warning in payload["warnings"]
    }


def test_treasury_pagination_shares_one_request_budget(mock_treasury, monkeypatch):
    times = iter([0.0, 1.0, 3.0])
    monkeypatch.setattr(
        "oracle_plugin.runtime_macro_rates_providers.monotonic", lambda: next(times)
    )
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        rows = (
            [_row("2026-08-31")] * int(request.url.params["page[size]"])
            if request.url.params["page[number]"] == "1"
            else [_row("2026-08-31", "Treasury Notes")]
        )
        return httpx.Response(200, json={"data": rows})

    mock_treasury(respond)
    payload = _lookup(seriesIds=[_series_id("Treasury Notes")], itemLimit=1)
    assert [row["seriesId"] for row in payload["series"]] == [_series_id("Treasury Notes")]
    timeouts = [request.extensions["timeout"]["read"] for request in requests]
    assert len(timeouts) == 2
    assert timeouts[0] - timeouts[1] == 2.0
    assert payload["warnings"] == []


def test_treasury_stops_pagination_when_request_budget_is_exhausted(mock_treasury, monkeypatch):
    times = iter([0.0, 0.0, 1000.0])
    monkeypatch.setattr(
        "oracle_plugin.runtime_macro_rates_providers.monotonic", lambda: next(times)
    )
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        size = int(request.url.params["page[size]"])
        return httpx.Response(200, json={"data": [_row("2026-08-31")] * size})

    mock_treasury(respond)
    payload = _lookup(seriesIds=[_series_id("Treasury Notes")], itemLimit=1)
    assert payload["series"] == []
    assert len(requests) == 1
    assert any(
        warning["code"] == "macro_rates_treasury_search_truncated"
        and "time budget" in warning["message"]
        for warning in payload["warnings"]
    )
